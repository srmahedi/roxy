"""
Custom Download Engine based on FDM Architecture
Implements multi-threaded downloading with resume support, speed limiting, and mirror URLs.
"""

import os
import threading
import time
import queue
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any
from urllib.parse import urlparse
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
        self.temp_file: str = ""
        
        # HTTP session
        self.session = None
        self.timeout: int = 30
        self.user_agent: str = "Roxy-Download-Engine/1.0"
        self.headers: Dict[str, str] = {}
        
        # Retry configuration
        self.max_retries: int = 3
        self.retry_delay: int = 5
        
    def create_session(self) -> requests.Session:
        """Create HTTP session with retry logic"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': self.user_agent,
            **self.headers
        })
        
        return session
    
    def query_file_info(self) -> bool:
        """Query file size and check resume support with HEAD and GET fallback"""
        try:
            if not self.session:
                self.session = self.create_session()
            
            response = None
            try:
                # First try HEAD request
                response = self.session.head(
                    self.url,
                    timeout=self.timeout,
                    allow_redirects=True
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
                        allow_redirects=True
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
                                self.temp_file = f"{self.output_file}.temp"

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
        self.temp_file = f"{self.output_file}.temp"
        
        # Reset state
        self.downloaded_bytes = 0
        self.sections.clear()
        self.mirrors.clear()
        self.current_mirror_index = 0
        self.stop_event.clear()

        # Check and resolve Google Drive URLs
        try:
            from utils.gdrive_resolver import is_google_drive_url, resolve_gdrive_download
            if is_google_drive_url(self.url):
                if not self.session:
                    self.session = self.create_session()
                cookies = self.headers.get('Cookie')
                referrer = self.headers.get('Referer')
                resolved_url, g_filename, g_size, g_error = resolve_gdrive_download(
                    self.url, session=self.session, cookies=cookies, referrer=referrer, timeout=self.timeout
                )
                if g_error:
                    self._emit_event('error', {'message': g_error})
                    return False
                if resolved_url:
                    self.url = resolved_url
                if g_size and g_size > 0:
                    self.file_size = g_size
                if g_filename:
                    cur_base = os.path.basename(self.output_file) if self.output_file else ""
                    cur_ext = os.path.splitext(cur_base)[1]
                    if not cur_ext or cur_base.lower() in ('download', 'file', 'index', 'view', 'preview'):
                        dir_name = os.path.dirname(self.output_file) if self.output_file else ""
                        self.output_file = os.path.join(dir_name, g_filename) if dir_name else g_filename
                        self.temp_file = f"{self.output_file}.temp"
        except Exception as e:
            print(f"DEBUG: Error resolving Google Drive URL: {e}")

        # Query file information (ignore return status, continue even if server blocks HEAD/GET)
        self.query_file_info()
        
        # Check for existing temp file (resume)
        if os.path.exists(self.temp_file):
            self._load_resume_state()
        
        # Create download sections
        self._create_sections()
        
        return True
    
    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL"""
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        return filename or 'downloaded_file'
    
    def _create_sections(self):
        """Create download sections based on file size and configuration"""
        self.sections.clear()
        
        # If size is unknown or resume is not supported, create a single section
        if self.file_size <= 0 or not self.resume_supported:
            end_pos = self.file_size - 1 if self.file_size > 0 else -1
            section = DownloadSection(
                section_id=0,
                start=0,
                end=end_pos,
                current=min(self.downloaded_bytes, max(0, self.file_size - 1)) if self.file_size > 0 else self.downloaded_bytes
            )
            self.sections.append(section)
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
                current=min(self.downloaded_bytes, self.file_size - 1)
            )
            self.sections.append(section)
            return

        section_size = self.file_size // num_sections
        for i in range(num_sections):
            start_pos = i * section_size
            end_pos = self.file_size - 1 if i == num_sections - 1 else (i + 1) * section_size - 1
            
            state = SectionState.STOPPED
            current_pos = start_pos
            if self.downloaded_bytes >= end_pos + 1:
                current_pos = end_pos + 1
                state = SectionState.DONE
            elif self.downloaded_bytes > start_pos:
                current_pos = self.downloaded_bytes

            section = DownloadSection(
                section_id=i,
                start=start_pos,
                end=end_pos,
                current=current_pos,
                state=state
            )
            self.sections.append(section)

    def _load_resume_state(self):
        """Load resume state from temp file"""
        try:
            if os.path.exists(self.temp_file):
                self.downloaded_bytes = os.path.getsize(self.temp_file)
                self._emit_event('resume_loaded', {
                    'downloaded_bytes': self.downloaded_bytes
                })
        except Exception as e:
            self._emit_event('error', {'message': f'Failed to load resume state: {str(e)}'})
    
    def start_download(self) -> bool:
        """Start the download process"""
        if self.state == DownloadState.DOWNLOADING:
            return False
        
        if not self.session:
            self.session = self.create_session()
        
        # Open output file for random-access binary read/write ('r+b' if exists, 'w+b' otherwise)
        try:
            out_dir = os.path.dirname(self.temp_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            if os.path.exists(self.temp_file):
                self.file_handle = open(self.temp_file, 'r+b')
            else:
                self.file_handle = open(self.temp_file, 'w+b')
        except Exception as e:
            self._emit_event('error', {'message': f'Failed to open output file: {str(e)}'})
            return False
        
        # Update state
        self.state = DownloadState.DOWNLOADING
        self._emit_event('download_started', {'url': self.url})
        
        # Start download threads for each section
        for section in self.sections:
            if section.state != SectionState.DONE:
                section.state = SectionState.DOWNLOADING
                thread = threading.Thread(
                    target=self._download_section,
                    args=(section,),
                    daemon=True
                )
                section.thread = thread
                thread.start()
                self.download_threads.append(thread)
        
        # Start progress monitoring thread
        monitor_thread = threading.Thread(
            target=self._monitor_progress,
            daemon=True
        )
        monitor_thread.start()
        self.download_threads.append(monitor_thread)
        
        return True
    
    def _download_section(self, section: DownloadSection):
        """Download a specific section"""
        url = self._get_current_url()
        
        while not self.stop_event.is_set() and section.state != SectionState.DONE:
            try:
                # Prepare headers for range request
                headers = {}
                if self.resume_supported:
                    if section.end > 0:
                        headers['Range'] = f'bytes={section.current}-{section.end}'
                    elif section.current > 0 and section.end != 0:
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
                    if "Download quota exceeded" in sample or ("quota" in sample.lower() and "exceeded" in sample.lower()):
                        err_msg = "Google Drive error: Download quota exceeded for this file. Try again later."
                    elif "You need access" in sample or "Sign in to continue" in sample or "accounts.google.com" in response.url:
                        err_msg = "Google Drive error: Authentication or permission required."
                    elif "404" in sample or "not found" in sample.lower():
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
                        section.state = SectionState.DONE
                        return
                    else:
                        with self.lock:
                            self.resume_supported = False
                            for s in self.sections:
                                if s.section_id != 0:
                                    s.state = SectionState.DONE
                            if section.end > 0 and self.file_size > 0:
                                section.end = self.file_size - 1
                
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

                        # Write to file safely
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

                        if section.end > 0 and section.current >= section.end + 1:
                            break
                
                # Section completed
                if not self.stop_event.is_set():
                    if (section.end > 0 and section.current >= section.end + 1) or section.end <= 0:
                        section.state = SectionState.DONE
                        self._emit_event('section_done', {
                            'section_id': section.section_id,
                            'bytes_downloaded': section.current - section.start
                        })
                
            except Exception as e:
                if self.stop_event.is_set():
                    section.state = SectionState.STOPPED
                else:
                    section.state = SectionState.ERROR
                    section.last_error = str(e)
                    self._emit_event('section_error', {
                        'section_id': section.section_id,
                        'error': str(e)
                    })
                    
                    # Retry logic
                    if not self.stop_event.is_set():
                        time.sleep(self.retry_delay)
                        # Try next mirror if available
                        if self._try_next_mirror():
                            continue
                        else:
                            with self.lock:
                                self.state = DownloadState.ERROR
                                self.stop_event.set()
                            self._emit_event('error', {'message': str(e)})
                            return
        
        # Check if all sections are done
        self._check_completion()
    
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
            all_done = all(section.state == SectionState.DONE for section in self.sections)
            
            if all_done and self.state == DownloadState.DOWNLOADING:
                self._finalize_download()
    
    def _finalize_download(self):
        """Finalize the download"""
        try:
            self.stop_event.set()

            # Close file handle safely
            with self.file_lock:
                if self.file_handle:
                    try:
                        self.file_handle.flush()
                        self.file_handle.close()
                    except Exception:
                        pass
                    self.file_handle = None

            # Safe atomic replace with retry loop for Windows
            if os.path.exists(self.temp_file):
                out_dir = os.path.dirname(self.output_file)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)

                replaced = False
                last_err = None
                for attempt in range(5):
                    try:
                        os.replace(self.temp_file, self.output_file)
                        replaced = True
                        break
                    except Exception as err:
                        last_err = err
                        time.sleep(0.2)

                if not replaced and os.path.exists(self.temp_file):
                    raise last_err or RuntimeError(f"Could not replace target file {self.output_file}")

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
            self.state = DownloadState.ERROR
            self._emit_event('error', {'message': f'Failed to finalize download: {str(e)}'})
    
    def pause_download(self):
        """Pause the download"""
        if self.state == DownloadState.DOWNLOADING:
            self.state = DownloadState.PAUSED
            self.stop_event.set()
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
        
        if self.session:
            self.session.close()
            self.session = None
        
        # Clean up temp file if download failed
        if self.state != DownloadState.DONE and os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except Exception:
                pass