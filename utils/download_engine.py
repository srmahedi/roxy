"""
Custom Download Engine based on FDM Architecture
Implements multi-threaded downloading with resume support, speed limiting, and mirror URLs.
Uses OkHttp via JPype for HTTP operations with fallback to requests.
"""

import os
import sys
import threading
import time
import queue
import hashlib
import glob
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any
from urllib.parse import urlparse

from utils.constants import TEMP_DOWNLOAD_DIR

# Try to initialize OkHttp with JPype, fallback to requests if not available
USE_OKHTTP = False
OkHttpClient = None
Request = None
TimeUnit = None

try:
    import jpype
    
    # OkHttp JVM initialization
    BASE_DIR = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    JAR_DIR = os.path.join(BASE_DIR, "okhttp")
    JARS = glob.glob(os.path.join(JAR_DIR, "*.jar"))
    
    if JARS and not jpype.isJVMStarted():
        try:
            jpype.startJVM(classpath=JARS)
            # Import OkHttp classes
            OkHttpClient = jpype.JClass("okhttp3.OkHttpClient")
            Request = jpype.JClass("okhttp3.Request")
            TimeUnit = jpype.JClass("java.util.concurrent.TimeUnit")
            USE_OKHTTP = True
            print("OkHttp initialized successfully")
        except Exception as e:
            print(f"Failed to initialize OkHttp: {e}, falling back to requests")
except Exception as e:
    print(f"JPype not available: {e}, using requests library")

# Import requests as fallback
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DownloadState(Enum):
    """Download states similar to FDM's state management"""
    STOPPED = 1
    DOWNLOADING = 2
    NEED_START = 4
    NEED_STOP = 8
    DONE = 16
    ERROR = 32
    PAUSED = 64


class SectionState(Enum):
    """Section states for individual download chunks"""
    DOWNLOADING = 1
    RECONNECTING = 2
    ERROR = 3
    DONE = 4
    STOPPED = 5


@dataclass
class DownloadSection:
    """Represents a download section/chunk similar to FDM's fsSection"""
    section_id: int
    start: int
    end: int
    current: int = 0
    state: SectionState = SectionState.STOPPED
    speed: int = 0
    last_error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    speed_limit: int = 0
    
    @property
    def size(self) -> int:
        return self.end - self.start + 1
    
    @property
    def remaining(self) -> int:
        return self.end - self.current
    
    @property
    def progress(self) -> float:
        if self.size == 0:
            return 0.0
        return (self.current - self.start) / self.size * 100


@dataclass
class MirrorURL:
    """Mirror URL information similar to FDM's mirror system"""
    url: str
    ping_time: float = float('inf')
    is_good: bool = True
    sections_active: int = 0


@dataclass
class DownloadEvent:
    """Download event for callback system"""
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)


class DownloadEngine:
    """
    Custom download engine based on FDM architecture.
    Implements multi-threaded downloading with resume support, speed limiting, and mirror URLs.
    """
    
    def __init__(self):
        self.url: str = ""
        self.output_file: str = ""
        self.file_size: int = 0
        self.downloaded_bytes: int = 0
        self.state: DownloadState = DownloadState.STOPPED
        
        # Download sections
        self.sections: List[DownloadSection] = []
        self.max_sections: int = 4
        self.min_section_size: int = 1024 * 1024  # 1MB
        self.fallback_to_single_thread: bool = False  # Fallback flag for problematic servers
        
        # Mirror URLs
        self.mirrors: List[MirrorURL] = []
        self.current_mirror_index: int = 0
        
        # Speed limiting
        self.speed_limit: int = 0  # 0 = unlimited
        self.speed_meter: List[int] = []
        self.speed_meter_lock = threading.Lock()
        
        # Thread management
        self.download_threads: List[threading.Thread] = []
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # File handling
        self.file_handle = None
        self.file_lock = threading.Lock()
        
        # Callbacks
        self.event_callback: Optional[Callable] = None
        self.progress_callback: Optional[Callable] = None
        
        # Resume support
        self.resume_supported: bool = False
        
        # HTTP client (OkHttp or requests)
        self.client = None
        self.session = None  # requests fallback
        self.timeout: int = 30
        self.user_agent: str = "Roxy-Download-Engine/1.0"
        self.headers: Dict[str, str] = {}
        
        # Retry configuration
        self.max_retries: int = 3
        self.retry_delay: int = 5

    def _get_metadata_file_path(self) -> str:
        """Get the path to the .meta file for this download."""
        if not self.output_file:
            return ""
        # Use hash of output file path to create unique .meta file name
        import hashlib
        file_hash = hashlib.md5(self.output_file.encode('utf-8')).hexdigest()
        return os.path.join(TEMP_DOWNLOAD_DIR, f"{file_hash}.meta")

    def _get_metadata(self) -> Dict[str, Any]:
        """Generate metadata dictionary for saving to .meta file."""
        if not self.output_file or not self.sections:
            return {}

        sections_data = [
            {
                'section_id': s.section_id,
                'start': s.start,
                'end': s.end,
                'current': s.current,
                'done': s.state == SectionState.DONE or (s.end > 0 and s.current >= s.end + 1)
            }
            for s in self.sections
        ]
        return {
            'url': self.url,
            'file_size': self.file_size,
            'downloaded_bytes': self.downloaded_bytes,
            'resume_supported': self.resume_supported,
            'fallback_to_single_thread': self.fallback_to_single_thread,
            'sections': sections_data,
            'updated_at': time.time(),
            'version': 1  # Metadata format version
        }

    def _save_meta_state(self):
        """Save section progress and download metadata to .meta file."""
        if not self.output_file or not self.sections:
            return

        try:
            with self.lock:
                meta_data = self._get_metadata()
                if not meta_data:
                    return

                # Get .meta file path
                meta_file = self._get_metadata_file_path()
                if not meta_file:
                    return

                # Ensure metadata directory exists
                meta_dir = os.path.dirname(meta_file)
                if meta_dir and not os.path.exists(meta_dir):
                    os.makedirs(meta_dir, exist_ok=True)

                # Serialize metadata to JSON and save
                with open(meta_file, 'w', encoding='utf-8') as f:
                    json.dump(meta_data, f, indent=2)

        except Exception as e:
            print(f"Failed to save metadata to .meta file: {e}")

    def delete_temp_files(self):
        """Safely close file handles and delete output file and metadata file."""
        with self.file_lock:
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None
        if self.output_file and os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
            except Exception as e:
                print(f"Could not remove output file: {e}")
        # Delete metadata file
        meta_file = self._get_metadata_file_path()
        if meta_file and os.path.exists(meta_file):
            try:
                os.remove(meta_file)
            except Exception as e:
                print(f"Could not remove metadata file: {e}")

    # ---------------------------------------------------------------------------
    # Known CDN / vendor download portals that gate downloads behind a Referer.
    # Maps a substring of the *download host* to the required Referer URL.
    # Add more entries here as needed.
    # ---------------------------------------------------------------------------
    _CDN_REFERER_MAP = {
        # AMD ---------------------------------------------------------------
        'drivers.amd.com':          'https://www.amd.com/en/support',
        'amd.com':                  'https://www.amd.com/en/support',
        # NVIDIA ------------------------------------------------------------
        'international.download.nvidia.com': 'https://www.nvidia.com/Download/index.aspx',
        'us.download.nvidia.com':   'https://www.nvidia.com/Download/index.aspx',
        'download.nvidia.com':      'https://www.nvidia.com/Download/index.aspx',
        'nvidia.com':               'https://www.nvidia.com/Download/index.aspx',
        # Intel -------------------------------------------------------------
        'downloadmirror.intel.com': 'https://www.intel.com/content/www/us/en/download-center/home.html',
        'download.intel.com':       'https://www.intel.com/content/www/us/en/download-center/home.html',
        'intel.com':                'https://www.intel.com/content/www/us/en/download-center/home.html',
        # Qualcomm ----------------------------------------------------------
        'releases.linaro.org':      'https://releases.linaro.org/',
        # Realtek -----------------------------------------------------------
        'dlcdnet.asus.com':         'https://www.asus.com/support/',
        'dlcdnets.asus.com':        'https://www.asus.com/support/',
        # SourceForge -------------------------------------------------------
        'sourceforge.net':          'https://sourceforge.net/',
        'downloads.sourceforge.net':'https://sourceforge.net/',
        # GitHub releases (CDN) ---------------------------------------------
        'objects.githubusercontent.com': 'https://github.com/',
        'github.com':               'https://github.com/',
        # Microsoft / Sysinternals ------------------------------------------
        'download.microsoft.com':   'https://www.microsoft.com/',
        'aka.ms':                   'https://www.microsoft.com/',
    }

    def _auto_referer(self) -> str:
        """Return an appropriate Referer header for the current download URL.

        Checks the URL host against _CDN_REFERER_MAP (longest match wins),
        then falls back to the origin (scheme + host) of the URL so the
        server at minimum sees a same-site referer rather than nothing.
        """
        if not self.url:
            return ''
        try:
            parsed = urlparse(self.url)
            host = parsed.netloc.lower()
            # Longest matching key wins (so 'drivers.amd.com' beats 'amd.com')
            best_key = ''
            best_referer = ''
            for cdn_host, referer in self._CDN_REFERER_MAP.items():
                if host == cdn_host or host.endswith('.' + cdn_host):
                    if len(cdn_host) > len(best_key):
                        best_key = cdn_host
                        best_referer = referer
            if best_referer:
                return best_referer
            # Fallback to same-origin referer
            return f"{parsed.scheme}://{host}/"
        except Exception:
            return ''
        
    def create_client(self):
        """Create HTTP client (OkHttp or requests) with configuration"""
        if USE_OKHTTP:
            builder = OkHttpClient().newBuilder()

            # Set timeout
            builder.connectTimeout(self.timeout, TimeUnit.SECONDS)
            builder.readTimeout(self.timeout, TimeUnit.SECONDS)
            builder.writeTimeout(self.timeout, TimeUnit.SECONDS)

            self.client = builder.build()
        else:
            # Fallback to requests
            self.session = requests.Session()

            # Configure retry strategy
            retry_strategy = Retry(
                total=self.max_retries,
                backoff_factor=1,
                status_forcelist=[408, 429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            # Disable automatic gzip decompression to avoid issues with range requests
            self.session.headers.update({
                'User-Agent': self.user_agent,
                'Accept-Encoding': 'identity',  # Disable compression
                **self.headers
            })
            # Inject auto-referer if no explicit referer is set
            if 'Referer' not in self.headers and 'referer' not in self.headers:
                auto_ref = self._auto_referer()
                if auto_ref:
                    self.session.headers['Referer'] = auto_ref

    def _refresh_session_headers(self):
        """Refresh the user-agent and extra headers on an already-open session."""
        if self.session is None:
            return
        self.session.headers['User-Agent'] = self.user_agent
        # Inject auto-referer if no explicit referer is set
        if 'Referer' not in self.headers and 'referer' not in self.headers:
            auto_ref = self._auto_referer()
            if auto_ref:
                self.session.headers['Referer'] = auto_ref
        # Re-apply any custom headers (cookies, referrer, etc.)
        for key, value in self.headers.items():
            self.session.headers[key] = value
    
    def query_file_info(self) -> bool:
        """Query file size and check resume support with HEAD and GET fallback"""
        try:
            if USE_OKHTTP:
                if not self.client:
                    self.create_client()
                
                response = None
                try:
                    # First try HEAD request
                    request_builder = Request.Builder().url(self.url).head()
                    request = request_builder.build()
                    response = self.client.newCall(request).execute()
                    
                    if response.code() not in (200, 206):
                        response.close()
                        response = None
                except Exception:
                    response = None

                # Fallback to GET request if HEAD failed
                if response is None:
                    try:
                        request_builder = Request.Builder().url(self.url).get()
                        request = request_builder.build()
                        response = self.client.newCall(request).execute()
                    except Exception:
                        response = None

                if response is not None:
                    # Get file size
                    content_length = response.header('content-length')
                    if content_length and content_length.isdigit():
                        self.file_size = int(content_length)
                    
                    # Check resume support
                    accept_ranges = response.header('accept-ranges')
                    if accept_ranges:
                        self.resume_supported = 'bytes' in accept_ranges.lower()
                    content_range = response.header('content-range')
                    if content_range:
                        self.resume_supported = True
                    
                    # Get suggested filename from Content-Disposition
                    content_disposition = response.header('content-disposition')
                    if content_disposition and 'filename' in content_disposition.lower():
                        import re
                        from utils.helpers import sanitize_filename
                        fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', content_disposition, re.IGNORECASE)
                        if fn_match:
                            suggested = sanitize_filename(fn_match.group(1).strip('"\''))
                            if suggested:
                                cur_base = os.path.basename(self.output_file) if self.output_file else ""
                                cur_ext = os.path.splitext(cur_base)[1]
                                
                                if not self.output_file or not cur_ext or cur_base.lower() in ('download', 'file', 'index', 'view'):
                                    dir_name = os.path.dirname(self.output_file) if self.output_file else ""
                                    self.output_file = os.path.join(dir_name, suggested) if dir_name else suggested

                    response.close()
                    
                    self._emit_event('file_info_queried', {
                        'file_size': self.file_size,
                        'resume_supported': self.resume_supported
                    })
                    
                    return True
                return False
            else:
                # Fallback to requests
                if not self.session:
                    self.create_client()
                
                response = None
                try:
                    # First try HEAD request
                    response = self.session.head(
                        self.url,
                        timeout=self.timeout,
                        allow_redirects=True,
                        headers={'Accept-Encoding': 'identity'}
                    )
                    if response.status_code not in (200, 206):
                        response = None
                except Exception:
                    response = None

                # Fallback to stream GET request if HEAD failed
                if response is None:
                    try:
                        response = self.session.get(
                            self.url,
                            stream=True,
                            timeout=self.timeout,
                            allow_redirects=True,
                            headers={'Accept-Encoding': 'identity'}
                        )
                    except Exception:
                        response = None

                if response is not None:
                    # Get file size
                    content_length = response.headers.get('content-length')
                    if content_length and content_length.isdigit():
                        self.file_size = int(content_length)
                    
                    # Check resume support
                    accept_ranges = response.headers.get('accept-ranges', '').lower()
                    self.resume_supported = 'bytes' in accept_ranges or 'content-range' in response.headers
                    
                    # Get suggested filename from Content-Disposition
                    content_disposition = response.headers.get('content-disposition', '')
                    if content_disposition and 'filename' in content_disposition.lower():
                        import re
                        from utils.helpers import sanitize_filename
                        fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', content_disposition, re.IGNORECASE)
                        if fn_match:
                            suggested = sanitize_filename(fn_match.group(1).strip('"\''))
                            if suggested:
                                cur_base = os.path.basename(self.output_file) if self.output_file else ""
                                cur_ext = os.path.splitext(cur_base)[1]
                                
                                if not self.output_file or not cur_ext or cur_base.lower() in ('download', 'file', 'index', 'view'):
                                    dir_name = os.path.dirname(self.output_file) if self.output_file else ""
                                    self.output_file = os.path.join(dir_name, suggested) if dir_name else suggested

                    if hasattr(response, 'close'):
                        response.close()
                    
                    self._emit_event('file_info_queried', {
                        'file_size': self.file_size,
                        'resume_supported': self.resume_supported
                    })
                    
                    return True
                return False
            
        except Exception as e:
            self._emit_event('error', {'message': f'Failed to query file info: {str(e)}'})
            return False
    
    def initialize_download(self, url: str, output_file: str = "") -> bool:
        """Initialize download with URL and output file"""
        self.url = url
        self.output_file = output_file or self._extract_filename(url)

        # Create output directory if it doesn't exist
        out_dir = os.path.dirname(self.output_file) or '.'
        os.makedirs(out_dir, exist_ok=True)

        # Reset state (but preserve downloaded_bytes if already set from restored state)
        saved_downloaded_bytes = self.downloaded_bytes
        self.downloaded_bytes = 0
        self.sections.clear()
        self.mirrors.clear()
        self.current_mirror_index = 0
        self.stop_event.clear()

        # Query file information (ignore return status, continue even if server blocks HEAD/GET)
        self.query_file_info()

        # Check for existing metadata file (resume)
        resume_loaded = False
        if os.path.exists(self._get_metadata_file_path()):
            resume_loaded = self._load_resume_state()

        # If no resume state was loaded, restore the saved downloaded_bytes from initialization
        if not resume_loaded or not self.sections:
            self.downloaded_bytes = saved_downloaded_bytes
            # Create download sections (only if not restored from metadata)
            self._create_sections()

        return True
    
    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL"""
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        return filename or 'downloaded_file'
    
    def _create_sections(self):
        """Create download sections based on file size and configuration"""
        # If sections were already restored from valid resume metadata, preserve them
        if self.sections:
            return

        self.sections.clear()

        # Auto-detect Google Drive URLs (which do not support multi-threaded Range requests)
        if self.url and ('googleusercontent.com' in self.url.lower() or 'drive.google.com' in self.url.lower()):
            self.fallback_to_single_thread = True

        # If fallback is enabled, size is unknown, or resume is not supported, create a single section
        if self.fallback_to_single_thread or self.file_size <= 0 or not self.resume_supported:
            end_pos = self.file_size - 1 if self.file_size > 0 else -1
            current_pos = min(self.downloaded_bytes, max(0, self.file_size - 1)) if (self.file_size > 0 and self.resume_supported) else 0
            section = DownloadSection(
                section_id=0,
                start=0,
                end=end_pos,
                current=current_pos,
                state=SectionState.STOPPED
            )
            self.sections.append(section)
            self._save_meta_state()
            return

        # Calculate section size
        num_sections = self.max_sections
        base_size = self.file_size // num_sections
        if base_size < self.min_section_size:
            num_sections = max(1, self.file_size // self.min_section_size)

        if num_sections <= 1:
            section = DownloadSection(
                section_id=0,
                start=0,
                end=self.file_size - 1,
                current=0,
                state=SectionState.STOPPED
            )
            self.sections.append(section)
            self._save_meta_state()
            return

        section_size = self.file_size // num_sections
        for i in range(num_sections):
            start_pos = i * section_size
            end_pos = self.file_size - 1 if i == num_sections - 1 else (i + 1) * section_size - 1

            section = DownloadSection(
                section_id=i,
                start=start_pos,
                end=end_pos,
                current=start_pos,
                state=SectionState.STOPPED
            )
            self.sections.append(section)

        self.downloaded_bytes = 0
        self._save_meta_state()

    def _load_resume_state(self) -> bool:
        """Load resume state from .meta file, verifying integrity against server info"""
        meta_file = self._get_metadata_file_path()
        if not meta_file or not os.path.exists(meta_file):
            self.downloaded_bytes = 0
            self.sections.clear()
            return False

        # Check if output file exists
        if not os.path.exists(self.output_file):
            print(f"Output file does not exist: {self.output_file}. Cannot resume.")
            self.delete_temp_files()
            self.downloaded_bytes = 0
            self.sections.clear()
            return False

        try:
            # Read metadata from .meta file
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # Validate URL
            meta_url = meta.get('url', '')
            if meta_url and self.url:
                parsed_saved = urlparse(meta_url)
                parsed_cur = urlparse(self.url)
                if parsed_saved.netloc != parsed_cur.netloc or parsed_saved.path != parsed_cur.path:
                    print("Saved metadata URL path does not match current URL. Starting fresh.")
                    self.delete_temp_files()
                    self.downloaded_bytes = 0
                    self.sections.clear()
                    return False

            # Validate file size if server returned file size
            meta_file_size = meta.get('file_size', 0)
            if self.file_size > 0 and meta_file_size > 0 and self.file_size != meta_file_size:
                print(f"Remote file size changed ({meta_file_size} -> {self.file_size}). Discarding old resume state.")
                self.delete_temp_files()
                self.downloaded_bytes = 0
                self.sections.clear()
                return False

            if self.file_size <= 0 and meta_file_size > 0:
                self.file_size = meta_file_size

            saved_sections = meta.get('sections', [])
            if not saved_sections:
                return False

            self.sections.clear()
            for s_data in saved_sections:
                s_id = s_data['section_id']
                s_start = s_data['start']
                s_end = s_data['end']
                s_cur = s_data.get('current', s_start)
                s_done = s_data.get('done', False) or (s_end > 0 and s_cur >= s_end + 1)

                sec = DownloadSection(
                    section_id=s_id,
                    start=s_start,
                    end=s_end,
                    current=s_cur,
                    state=SectionState.DONE if s_done else SectionState.STOPPED
                )
                self.sections.append(sec)

            self.fallback_to_single_thread = meta.get('fallback_to_single_thread', self.fallback_to_single_thread)
            self.downloaded_bytes = sum(max(0, s.current - s.start) for s in self.sections)
            if self.file_size > 0:
                self.downloaded_bytes = min(self.file_size, self.downloaded_bytes)

            print(f"Successfully restored resume state: {self.downloaded_bytes}/{self.file_size} bytes across {len(self.sections)} sections")
            self._emit_event('resume_loaded', {
                'downloaded_bytes': self.downloaded_bytes,
                'file_size': self.file_size,
                'sections_count': len(self.sections)
            })
            return True

        except Exception as e:
            print(f"ERROR reading resume metadata: {e}")
            self.downloaded_bytes = 0
            self.sections.clear()
            return False

    def start_download(self) -> bool:
        """Start the download process"""
        if self.state == DownloadState.DOWNLOADING:
            return False
        
        if USE_OKHTTP:
            if not self.client:
                self.create_client()
        else:
            if not self.session:
                self.create_client()
        
        # Open output file for random-access binary read/write ('r+b' if exists, 'w+b' otherwise)
        try:
            if os.path.exists(self.output_file):
                self.file_handle = open(self.output_file, 'r+b')
            else:
                self.file_handle = open(self.output_file, 'w+b')
        except Exception as e:
            self._emit_event('error', {'message': f'Failed to open output file: {str(e)}'})
            return False
        
        # Update state
        self.state = DownloadState.DOWNLOADING
        self.stop_event.clear()
        self._emit_event('download_started', {'url': self.url})
        self._save_meta_state()

        # Determine number of worker threads
        if self.fallback_to_single_thread:
            num_workers = 1
        else:
            num_workers = min(len(self.sections), self.max_sections) if self.sections else 1

        self.download_threads.clear()

        # Start worker threads
        for i in range(num_workers):
            thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"DownloadWorker-{i}"
            )
            thread.start()
            self.download_threads.append(thread)
        
        # Start progress monitoring thread
        monitor_thread = threading.Thread(
            target=self._monitor_progress,
            daemon=True,
            name="ProgressMonitor"
        )
        monitor_thread.start()
        self.download_threads.append(monitor_thread)
        
        return True

    def _worker_loop(self):
        """Worker loop to process unfinished download sections sequentially or in parallel"""
        while not self.stop_event.is_set():
            section_to_download = None
            with self.lock:
                for s in self.sections:
                    if s.state in (SectionState.STOPPED, SectionState.ERROR):
                        if s.end > 0 and s.current >= s.end + 1:
                            s.state = SectionState.DONE
                        else:
                            s.state = SectionState.DOWNLOADING
                            section_to_download = s
                            break

            if not section_to_download:
                break

            url = self._get_current_url()
            if USE_OKHTTP:
                self._download_section_okhttp(section_to_download, url)
            else:
                self._download_section_requests(section_to_download, url)

            self._check_completion()

    def _download_section(self, section: DownloadSection):
        """Download a specific section"""
        url = self._get_current_url()
        
        if USE_OKHTTP:
            self._download_section_okhttp(section, url)
        else:
            self._download_section_requests(section, url)
        
        # Check if all sections are done
        self._check_completion()
    
    def _download_section_okhttp(self, section: DownloadSection, url: str):
        """Download a specific section using OkHttp"""
        retry_count = 0
        while not self.stop_event.is_set() and section.state != SectionState.DONE:
            try:
                # If section is already completed, mark DONE and exit
                if section.end > 0 and section.current >= section.end + 1:
                    section.state = SectionState.DONE
                    return

                # Prepare request builder
                request_builder = Request.Builder().url(url)
                
                # Add custom headers
                for key, value in self.headers.items():
                    request_builder.addHeader(key, value)
                
                # Use Range header if resume is supported and not starting from 0 to end of file
                if self.resume_supported and (section.start > 0 or section.current > 0 or section.end > 0):
                    if section.end > 0:
                        request_builder.addHeader("Range", f'bytes={section.current}-{section.end}')
                    elif section.current > 0:
                        request_builder.addHeader("Range", f'bytes={section.current}-')
                
                request = request_builder.build()
                response = self.client.newCall(request).execute()
                
                if not response.isSuccessful():
                    raise Exception(f"HTTP {response.code()}: {response.message()}")

                # Safety check: Detect if server returned an HTML error/webpage instead of expected binary file
                content_type = response.header('content-type')
                if content_type:
                    content_type = content_type.lower()
                target_ext = os.path.splitext(self.output_file)[1].lower() if self.output_file else ""
                if content_type and 'text/html' in content_type and target_ext not in ('.html', '.htm'):
                    body = response.body()
                    try:
                        sample_bytes = body.byteStream().read(4096)
                        sample = bytes(sample_bytes).decode('utf-8', errors='ignore')
                    except Exception:
                        sample = ""
                    err_msg = "Server returned an HTML page instead of the requested file"
                    if "404" in sample or "not found" in sample.lower():
                        err_msg = "File not found (404)."

                    with self.lock:
                        section.state = SectionState.ERROR
                        section.last_error = err_msg
                        self.state = DownloadState.ERROR
                        self.stop_event.set()
                    try:
                        if self.file_handle:
                            with self.file_lock:
                                self.file_handle.close()
                                self.file_handle = None
                    except Exception:
                        pass
                    body.close()
                    response.close()
                    self._emit_event('error', {'message': err_msg})
                    return

                # Check if range request was sent but server returned 200 OK (ignored Range)
                range_header = request.header("Range")
                if range_header and response.code() == 200:
                    body = response.body()
                    if section.section_id != 0:
                        section.state = SectionState.STOPPED
                        body.close()
                        response.close()
                        return
                    else:
                        with self.lock:
                            self.resume_supported = False
                            self.fallback_to_single_thread = True
                            for s in self.sections:
                                if s.section_id != 0:
                                    s.state = SectionState.STOPPED
                            section.start = 0
                            section.current = 0
                            if section.end > 0 and self.file_size > 0:
                                section.end = self.file_size - 1
                        with self.file_lock:
                            if self.file_handle and not self.file_handle.closed:
                                self.file_handle.seek(0)
                                self.file_handle.truncate(0)
                        self.downloaded_bytes = 0
                        self._save_meta_state()
                
                # Update section end and file size if unknown
                content_length = response.header('content-length')
                if content_length and content_length.isdigit():
                    cl = int(content_length)
                    if section.end <= 0:
                        section.end = section.current + cl - 1
                    with self.lock:
                        if self.file_size <= 0:
                            self.file_size = section.current + cl

                content_range = response.header('content-range')
                if content_range:
                    import re
                    cr_match = re.search(r'bytes\s+\d+-\d+/(\d+)', content_range, re.IGNORECASE)
                    if cr_match:
                        with self.lock:
                            self.file_size = int(cr_match.group(1))
                
                # Download data
                body = response.body()
                input_stream = body.byteStream()
                chunk_size = 8192
                
                while not self.stop_event.is_set():
                    chunk = input_stream.read(chunk_size)
                    if chunk is None or len(chunk) == 0:
                        break
                    
                    # Convert Java byte array to Python bytes
                    python_chunk = bytes(chunk)
                    
                    # Apply speed limit
                    if self.speed_limit > 0:
                        self._apply_speed_limit(len(python_chunk))
                    
                    actual_chunk_size = len(python_chunk)

                    # Prevent writing past section end if section end is defined
                    if section.end > 0 and section.current + actual_chunk_size > section.end + 1:
                        actual_chunk_size = max(0, section.end + 1 - section.current)
                        python_chunk = python_chunk[:actual_chunk_size]

                    if actual_chunk_size <= 0:
                        break

                    # Write to file safely (no metadata header offset)
                    with self.file_lock:
                        if self.file_handle and not self.file_handle.closed:
                            self.file_handle.seek(section.current)
                            self.file_handle.write(python_chunk)
                        else:
                            break
                    
                    # Update progress
                    with self.lock:
                        section.current += actual_chunk_size
                        section.speed = actual_chunk_size
                        if self.sections:
                            calculated_bytes = sum(max(0, s.current - s.start) for s in self.sections)
                            if self.file_size > 0:
                                self.downloaded_bytes = min(self.file_size, calculated_bytes)
                            else:
                                self.downloaded_bytes = calculated_bytes

                    retry_count = 0

                    if section.end > 0 and section.current >= section.end + 1:
                        break
                
                body.close()
                response.close()
                
                # Section completed
                if not self.stop_event.is_set():
                    if (section.end > 0 and section.current >= section.end + 1) or (section.end <= 0 and response.code() == 200):
                        section.state = SectionState.DONE
                        self._save_meta_state()
                        self._emit_event('section_done', {
                            'section_id': section.section_id,
                            'bytes_downloaded': section.current - section.start
                        })
                        return
                
            except Exception as e:
                if self.stop_event.is_set():
                    section.state = SectionState.STOPPED
                    return
                else:
                    section.last_error = str(e)
                    print(f"DEBUG: OkHttp Section {section.section_id} error: {e}")

                    # Try next mirror if available
                    if self._try_next_mirror():
                        continue

                    # Transient retry
                    retry_count += 1
                    if retry_count <= self.max_retries and not self.stop_event.is_set():
                        print(f"Retrying section {section.section_id} ({retry_count}/{self.max_retries}) in {self.retry_delay}s...")
                        time.sleep(self.retry_delay)
                        continue

                    section.state = SectionState.ERROR
                    self._save_meta_state()
                    with self.lock:
                        self.state = DownloadState.ERROR
                        self.stop_event.set()
                    self._emit_event('section_error', {
                        'section_id': section.section_id,
                        'error': str(e)
                    })
                    self._emit_event('error', {'message': f'Network error: {str(e)}'})
                    return
    
    def _download_section_requests(self, section: DownloadSection, url: str):
        """Download a specific section using requests (fallback)"""
        retry_count = 0
        while not self.stop_event.is_set() and section.state != SectionState.DONE:
            try:
                # If section is already completed, mark DONE and exit
                if section.end > 0 and section.current >= section.end + 1:
                    section.state = SectionState.DONE
                    return

                # Prepare headers for range request
                headers = self.headers.copy()  # Include stored headers (cookies, referrer, etc.)
                headers['Accept-Encoding'] = 'identity'
                
                # Use Range header if resume is supported and not starting from 0 to end of file
                if self.resume_supported and (section.start > 0 or section.current > 0 or section.end > 0):
                    if section.end > 0:
                        headers['Range'] = f'bytes={section.current}-{section.end}'
                    elif section.current > 0:
                        headers['Range'] = f'bytes={section.current}-'
                
                # Make request
                response = self.session.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=self.timeout
                )
                response.raise_for_status()

                # Safety check: Detect if server returned an HTML error/webpage instead of expected binary file
                content_type = response.headers.get('content-type', '').lower()
                target_ext = os.path.splitext(self.output_file)[1].lower() if self.output_file else ""
                if 'text/html' in content_type and target_ext not in ('.html', '.htm'):
                    try:
                        sample_chunk = next(response.iter_content(chunk_size=4096), b'')
                        sample = sample_chunk.decode('utf-8', errors='ignore')
                    except Exception:
                        sample = ""
                    err_msg = "Server returned an HTML page instead of the requested file"
                    if "404" in sample or "not found" in sample.lower():
                        err_msg = "File not found (404)."

                    with self.lock:
                        section.state = SectionState.ERROR
                        section.last_error = err_msg
                        self.state = DownloadState.ERROR
                        self.stop_event.set()
                    try:
                        if self.file_handle:
                            with self.file_lock:
                                self.file_handle.close()
                                self.file_handle = None
                    except Exception:
                        pass
                    self._emit_event('error', {'message': err_msg})
                    response.close()
                    return

                # Check if range request was sent but server returned 200 OK (ignored Range)
                if 'Range' in headers and response.status_code == 200:
                    if section.section_id != 0:
                        section.state = SectionState.STOPPED
                        response.close()
                        return
                    else:
                        with self.lock:
                            self.resume_supported = False
                            self.fallback_to_single_thread = True
                            for s in self.sections:
                                if s.section_id != 0:
                                    s.state = SectionState.STOPPED
                            section.start = 0
                            section.current = 0
                            if section.end > 0 and self.file_size > 0:
                                section.end = self.file_size - 1
                        with self.file_lock:
                            if self.file_handle and not self.file_handle.closed:
                                self.file_handle.seek(0)
                                self.file_handle.truncate(0)
                        self.downloaded_bytes = 0
                        self._save_meta_state()
                
                # Update section end and file size if unknown
                content_length = response.headers.get('content-length')
                if content_length and content_length.isdigit():
                    cl = int(content_length)
                    if section.end <= 0:
                        section.end = section.current + cl - 1
                    with self.lock:
                        if self.file_size <= 0:
                            self.file_size = section.current + cl

                content_range = response.headers.get('content-range')
                if content_range:
                    import re
                    cr_match = re.search(r'bytes\s+\d+-\d+/(\d+)', content_range, re.IGNORECASE)
                    if cr_match:
                        with self.lock:
                            self.file_size = int(cr_match.group(1))
                
                # Download data
                for chunk in response.iter_content(chunk_size=8192):
                    if self.stop_event.is_set():
                        break
                    
                    if chunk:
                        # Apply speed limit
                        if self.speed_limit > 0:
                            self._apply_speed_limit(len(chunk))
                        
                        chunk_size = len(chunk)

                        # Prevent writing past section end if section end is defined
                        if section.end > 0 and section.current + chunk_size > section.end + 1:
                            chunk_size = max(0, section.end + 1 - section.current)
                            chunk = chunk[:chunk_size]

                        if chunk_size <= 0:
                            break

                        # Write to file safely (no metadata header offset)
                        with self.file_lock:
                            if self.file_handle and not self.file_handle.closed:
                                self.file_handle.seek(section.current)
                                self.file_handle.write(chunk)
                            else:
                                break
                        
                        # Update progress
                        with self.lock:
                            section.current += chunk_size
                            section.speed = chunk_size
                            if self.sections:
                                calculated_bytes = sum(max(0, s.current - s.start) for s in self.sections)
                                if self.file_size > 0:
                                    self.downloaded_bytes = min(self.file_size, calculated_bytes)
                                else:
                                    self.downloaded_bytes = calculated_bytes

                        retry_count = 0

                        if section.end > 0 and section.current >= section.end + 1:
                            break
                
                response.close()

                # Section completed
                if not self.stop_event.is_set():
                    if (section.end > 0 and section.current >= section.end + 1) or (section.end <= 0 and response.status_code == 200):
                        section.state = SectionState.DONE
                        self._save_meta_state()
                        self._emit_event('section_done', {
                            'section_id': section.section_id,
                            'bytes_downloaded': section.current - section.start
                        })
                        return

            except Exception as e:
                if self.stop_event.is_set():
                    section.state = SectionState.STOPPED
                    return
                else:
                    section.last_error = str(e)
                    print(f"DEBUG: Requests Section {section.section_id} error: {e}")

                    # Try next mirror if available
                    if self._try_next_mirror():
                        continue

                    # Transient retry
                    retry_count += 1
                    if retry_count <= self.max_retries and not self.stop_event.is_set():
                        print(f"Retrying section {section.section_id} ({retry_count}/{self.max_retries}) in {self.retry_delay}s...")
                        time.sleep(self.retry_delay)
                        continue

                    section.state = SectionState.ERROR
                    self._save_meta_state()
                    with self.lock:
                        self.state = DownloadState.ERROR
                        self.stop_event.set()
                    self._emit_event('section_error', {
                        'section_id': section.section_id,
                        'error': str(e)
                    })
                    self._emit_event('error', {'message': f'Network error: {str(e)}'})
                    return
    
    def _get_current_url(self) -> str:
        """Get current URL to download from (main or mirror)"""
        if self.mirrors and self.current_mirror_index < len(self.mirrors):
            return self.mirrors[self.current_mirror_index].url
        return self.url
    
    def _try_next_mirror(self) -> bool:
        """Try to switch to next mirror URL"""
        if self.current_mirror_index + 1 < len(self.mirrors):
            self.current_mirror_index += 1
            self._emit_event('mirror_switched', {
                'mirror_index': self.current_mirror_index,
                'url': self.mirrors[self.current_mirror_index].url
            })
            return True
        return False
    
    def _apply_speed_limit(self, chunk_size: int):
        """Apply speed limiting by sleeping if necessary"""
        if self.speed_limit <= 0:
            return
        
        # Calculate current speed (bytes per second)
        with self.speed_meter_lock:
            if self.speed_meter:
                current_speed = sum(self.speed_meter[-10:]) / 10  # Average of last 10 measurements
            else:
                current_speed = 0
        
        # If we're exceeding the limit, sleep
        if current_speed > self.speed_limit:
            excess_ratio = current_speed / self.speed_limit
            sleep_time = (chunk_size / self.speed_limit) * (excess_ratio - 1)
            time.sleep(max(0, sleep_time))
    
    def _monitor_progress(self):
        """Monitor download progress and emit callbacks"""
        last_time = time.time()
        last_bytes = self.downloaded_bytes
        last_save_time = time.time()
        
        while not self.stop_event.is_set() and self.state == DownloadState.DOWNLOADING:
            time.sleep(0.5)  # Update every 500ms
            
            now = time.time()
            dt = now - last_time
            if dt <= 0:
                dt = 0.5
            
            current_bytes = self.downloaded_bytes
            bytes_delta = current_bytes - last_bytes
            if bytes_delta < 0:
                bytes_delta = 0
            
            current_speed = bytes_delta / dt
            last_time = now
            last_bytes = current_bytes
            
            # Calculate progress
            progress = 0.0
            if self.file_size > 0:
                progress = (self.downloaded_bytes / self.file_size) * 100
            
            # Save meta state every 2 seconds (balance between realtime and performance)
            # Important events (section completion, errors) trigger immediate saves already
            if now - last_save_time >= 2.0:
                self._save_meta_state()
                last_save_time = now

            # Emit progress callback
            if self.progress_callback:
                self.progress_callback({
                    'downloaded_bytes': self.downloaded_bytes,
                    'file_size': self.file_size,
                    'progress': progress,
                    'speed': current_speed
                })
    
    def _check_completion(self):
        """Check if all sections are completed"""
        with self.lock:
            if not self.sections or self.state != DownloadState.DOWNLOADING:
                return

            all_done = True
            for section in self.sections:
                if section.state != SectionState.DONE:
                    if section.end > 0 and section.current >= section.end + 1:
                        section.state = SectionState.DONE
                    else:
                        all_done = False
                        break

            # If total file size is known, verify that the sum of downloaded bytes equals or exceeds file_size
            if all_done and self.file_size > 0:
                total_downloaded = sum(max(0, s.current - s.start) for s in self.sections)
                if total_downloaded < self.file_size:
                    all_done = False

            if all_done and self.state == DownloadState.DOWNLOADING:
                self._finalize_download()
    
    def _finalize_download(self):
        """Finalize the download - file is already at final location"""
        try:
            self.stop_event.set()

            # Close file handle safely
            with self.file_lock:
                if self.file_handle:
                    try:
                        self.file_handle.flush()
                        self.file_handle.close()
                    except Exception as e:
                        print(f"WARNING: Error closing file handle: {e}")
                    self.file_handle = None

            # Delete .meta file after successful completion
            meta_file = self._get_metadata_file_path()
            if meta_file and os.path.exists(meta_file):
                try:
                    os.remove(meta_file)
                except Exception as e:
                    print(f"WARNING: Could not delete metadata file: {e}")

            if os.path.exists(self.output_file):
                actual_size = os.path.getsize(self.output_file)
                self.downloaded_bytes = actual_size
                if self.file_size <= 0:
                    self.file_size = actual_size

            # Update state
            self.state = DownloadState.DONE
            self._emit_event('download_complete', {
                'file_size': self.file_size,
                'downloaded_bytes': self.downloaded_bytes,
                'output_file': self.output_file
            })

        except Exception as e:
            print(f"CRITICAL ERROR in finalize: {e}")
            self.state = DownloadState.ERROR
            self._emit_event('error', {'message': f'Failed to finalize download: {str(e)}'})
    
    def pause_download(self):
        """Pause the download"""
        if self.state == DownloadState.DOWNLOADING:
            self.state = DownloadState.PAUSED
            self.stop_event.set()
            with self.lock:
                for s in self.sections:
                    if s.state == SectionState.DOWNLOADING:
                        s.state = SectionState.STOPPED
            self._save_meta_state()
            self._emit_event('download_paused', {})
    
    def resume_download(self) -> bool:
        """Resume the download"""
        if self.state == DownloadState.PAUSED:
            self.stop_event.clear()
            return self.start_download()
        return False
    
    def stop_download(self):
        """Stop the download"""
        self.stop_event.set()
        
        # Wait for threads to finish
        for thread in self.download_threads:
            if thread != threading.current_thread() and thread.is_alive():
                thread.join(timeout=1.0)
        
        # Close file handle
        with self.file_lock:
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None

        with self.lock:
            for s in self.sections:
                if s.state == SectionState.DOWNLOADING:
                    s.state = SectionState.STOPPED
        self._save_meta_state()

        if self.state in [DownloadState.DOWNLOADING, DownloadState.PAUSED]:
            self.state = DownloadState.STOPPED
            self._emit_event('download_stopped', {})
    
    def add_mirror(self, url: str):
        """Add a mirror URL"""
        mirror = MirrorURL(url=url)
        self.mirrors.append(mirror)
        self._emit_event('mirror_added', {'url': url})
    
    def set_speed_limit(self, limit: int):
        """Set speed limit in bytes per second (0 = unlimited)"""
        self.speed_limit = limit
        self._emit_event('speed_limit_changed', {'limit': limit})
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current download progress"""
        progress = 0.0
        if self.file_size > 0:
            progress = (self.downloaded_bytes / self.file_size) * 100
        
        with self.speed_meter_lock:
            if self.speed_meter:
                speed = sum(self.speed_meter) / len(self.speed_meter)
            else:
                speed = 0
        
        return {
            'state': self.state.name,
            'downloaded_bytes': self.downloaded_bytes,
            'file_size': self.file_size,
            'progress': progress,
            'speed': speed,
            'sections': len(self.sections),
            'active_sections': sum(1 for s in self.sections if s.state == SectionState.DOWNLOADING)
        }
    
    def set_event_callback(self, callback: Callable):
        """Set callback for download events"""
        self.event_callback = callback
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit download event"""
        if self.event_callback:
            event = DownloadEvent(event_type=event_type, data=data)
            self.event_callback(event)
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_download()
        
        if USE_OKHTTP and self.client:
            try:
                self.client.dispatcher().executorService().shutdown()
                self.client.connectionPool().evictAll()
            except Exception:
                pass
            self.client = None
        elif not USE_OKHTTP and self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None