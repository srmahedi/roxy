"""
HLS / M3U8 Download Engine for Roxy Download Manager
Implements downloading, multi-threaded segment fetching, AES-128 decryption, and stitching for HLS streams.
"""

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, List, Dict, Any
from urllib.parse import urljoin, urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.download_engine import DownloadState, DownloadEvent


@dataclass
class HLSSegment:
    """Represents a single HLS media segment"""
    index: int
    url: str
    duration: float
    key_url: Optional[str] = None
    key_iv: Optional[bytes] = None
    key_bytes: Optional[bytes] = None
    downloaded: bool = False
    file_path: str = ""
    size_bytes: int = 0


class HLSEngine:
    """
    HLS Download Engine supporting master playlist variant selection,
    multi-threaded segment fetching, AES-128 decryption, and segment stitching.
    Shares event and progress interface with DownloadEngine.
    """

    def __init__(self):
        self.url: str = ""
        self.output_file: str = ""
        self.file_size: int = 0  # Total downloaded bytes (or estimated)
        self.downloaded_bytes: int = 0
        self.state: DownloadState = DownloadState.STOPPED

        # HLS Segments
        self.segments: List[HLSSegment] = []
        self.max_threads: int = 4
        self.temp_dir: str = ""
        self.key_cache: Dict[str, bytes] = {}

        # Speed limiting & Progress
        self.speed_limit: int = 0  # 0 = unlimited
        self.user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.headers: Dict[str, str] = {}
        self.session: Optional[requests.Session] = None
        self.timeout: int = 30

        # Threading
        self.download_threads: List[threading.Thread] = []
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # Callbacks
        self.event_callback: Optional[Callable] = None
        self.progress_callback: Optional[Callable] = None
        self.resume_supported: bool = True

    def create_session(self) -> requests.Session:
        """Create HTTP session with retry logic"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
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

    def initialize_download(self, url: str, output_file: str = "") -> bool:
        """Initialize HLS download with playlist parsing"""
        self.url = url
        if not output_file:
            parsed = urlparse(url)
            base_name = os.path.splitext(os.path.basename(parsed.path))[0] or "hls_video"
            output_file = f"{base_name}.mp4"
        elif not output_file.lower().endswith(('.mp4', '.ts', '.mkv')):
            output_file += ".mp4"

        self.output_file = output_file
        self.temp_dir = f"{self.output_file}.hls_tmp"
        os.makedirs(self.temp_dir, exist_ok=True)

        self.downloaded_bytes = 0
        self.file_size = 0
        self.segments.clear()
        self.key_cache.clear()
        self.stop_event.clear()

        if not self.session:
            self.session = self.create_session()

        return self.parse_playlist(self.url)

    def parse_playlist(self, playlist_url: str) -> bool:
        """Parse master or media playlist"""
        try:
            resp = self.session.get(playlist_url, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.text

            # Check if this is a master playlist
            if "#EXT-X-STREAM-INF" in content:
                # Master playlist: find highest bandwidth variant
                best_variant_url = self._extract_best_variant(content, playlist_url)
                if best_variant_url:
                    return self.parse_playlist(best_variant_url)
                return False

            # Media playlist: parse segments
            return self._parse_media_playlist(content, playlist_url)

        except Exception as e:
            self._emit_event('error', {'message': f'Failed to parse HLS playlist: {str(e)}'})
            return False

    def _extract_best_variant(self, content: str, base_url: str) -> Optional[str]:
        """Extract variant URL with highest bandwidth from master playlist"""
        lines = content.splitlines()
        max_bandwidth = -1
        best_url = None

        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("#EXT-X-STREAM-INF"):
                match = re.search(r'BANDWIDTH=(\d+)', line)
                bandwidth = int(match.group(1)) if match else 0

                # Next non-empty non-comment line is the URI
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith("#"):
                        variant_url = urljoin(base_url, next_line)
                        if bandwidth > max_bandwidth:
                            max_bandwidth = bandwidth
                            best_url = variant_url
                        break
        return best_url or (lines[-1].strip() if lines else None)

    def _parse_media_playlist(self, content: str, playlist_url: str) -> bool:
        """Parse media playlist for segments and keys"""
        lines = content.splitlines()
        current_key_url = None
        current_key_iv = None
        segment_index = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXT-X-KEY"):
                # Handle AES-128 key
                method_match = re.search(r'METHOD=([^,\s]+)', line)
                method = method_match.group(1) if method_match else ""

                if method == "AES-128":
                    uri_match = re.search(r'URI="([^"]+)"', line)
                    if uri_match:
                        current_key_url = urljoin(playlist_url, uri_match.group(1))

                    iv_match = re.search(r'IV=0x([0-9a-fA-F]+)', line)
                    if iv_match:
                        iv_hex = iv_match.group(1)
                        if len(iv_hex) % 2 != 0:
                            iv_hex = "0" + iv_hex
                        current_key_iv = bytes.fromhex(iv_hex)
                    else:
                        current_key_iv = None
                else:
                    current_key_url = None
                    current_key_iv = None

            elif line.startswith("#EXTINF"):
                match = re.search(r'#EXTINF:([0-9.]+)', line)
                duration = float(match.group(1)) if match else 0.0

            elif not line.startswith("#"):
                segment_url = urljoin(playlist_url, line)
                seg_path = os.path.join(self.temp_dir, f"seg_{segment_index:05d}.ts")

                segment = HLSSegment(
                    index=segment_index,
                    url=segment_url,
                    duration=duration if 'duration' in locals() else 0.0,
                    key_url=current_key_url,
                    key_iv=current_key_iv or segment_index.to_bytes(16, 'big'),
                    file_path=seg_path
                )
                self.segments.append(segment)
                segment_index += 1

        self._emit_event('file_info_queried', {
            'file_size': 0,
            'segments_count': len(self.segments),
            'resume_supported': True
        })
        return len(self.segments) > 0

    def start_download(self) -> bool:
        """Start downloading HLS segments concurrently"""
        if self.state == DownloadState.DOWNLOADING or not self.segments:
            return False

        if not self.session:
            self.session = self.create_session()

        self.state = DownloadState.DOWNLOADING
        self._emit_event('download_started', {'url': self.url})

        # Fetch keys in advance if needed
        for seg in self.segments:
            if seg.key_url and seg.key_url not in self.key_cache:
                try:
                    res = self.session.get(seg.key_url, timeout=self.timeout)
                    res.raise_for_status()
                    self.key_cache[seg.key_url] = res.content
                except Exception as e:
                    self._emit_event('error', {'message': f'Failed to fetch AES key: {str(e)}'})
                    self.state = DownloadState.ERROR
                    return False

        # Segment queue
        segment_queue = [seg for seg in self.segments if not seg.downloaded]

        # Launch worker threads
        num_threads = min(self.max_threads, len(segment_queue))
        for i in range(num_threads):
            t = threading.Thread(
                target=self._worker_loop,
                args=(segment_queue,),
                daemon=True
            )
            t.start()
            self.download_threads.append(t)

        # Launch progress monitor thread
        monitor_thread = threading.Thread(
            target=self._monitor_progress,
            daemon=True
        )
        monitor_thread.start()
        self.download_threads.append(monitor_thread)

        return True

    def _worker_loop(self, queue: List[HLSSegment]):
        """Worker loop processing segment downloads"""
        while not self.stop_event.is_set():
            segment = None
            with self.lock:
                if not queue:
                    break
                segment = queue.pop(0)

            if segment:
                self._download_single_segment(segment)

        self._check_completion()

    def _download_single_segment(self, segment: HLSSegment):
        """Download and decrypt a single segment"""
        try:
            res = self.session.get(segment.url, timeout=self.timeout)
            res.raise_for_status()
            data = res.content

            # Decrypt if key is specified
            if segment.key_url and segment.key_url in self.key_cache:
                key_bytes = self.key_cache[segment.key_url]
                data = self._decrypt_aes_128(data, key_bytes, segment.key_iv)

            with open(segment.file_path, "wb") as f:
                f.write(data)

            segment.size_bytes = len(data)
            segment.downloaded = True

            with self.lock:
                self.downloaded_bytes += segment.size_bytes

        except Exception as e:
            if not self.stop_event.is_set():
                self._emit_event('section_error', {
                    'section_id': segment.index,
                    'error': str(e)
                })

    def _decrypt_aes_128(self, data: bytes, key: bytes, iv: bytes) -> bytes:
        """Decrypt AES-128 encrypted segment data"""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend

            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(data) + decryptor.finalize()

            # Remove PKCS7 padding
            pad_len = decrypted[-1]
            if 1 <= pad_len <= 16:
                decrypted = decrypted[:-pad_len]
            return decrypted
        except ImportError:
            # Fallback if cryptography module is not installed
            return data

    def _monitor_progress(self):
        """Monitor progress and trigger callback updates"""
        last_time = time.time()
        last_bytes = self.downloaded_bytes

        while not self.stop_event.is_set() and self.state == DownloadState.DOWNLOADING:
            time.sleep(0.5)

            now = time.time()
            dt = max(0.5, now - last_time)

            with self.lock:
                current_bytes = self.downloaded_bytes
                completed_segs = sum(1 for s in self.segments if s.downloaded)
                total_segs = len(self.segments)

            bytes_delta = max(0, current_bytes - last_bytes)
            current_speed = bytes_delta / dt
            last_time = now
            last_bytes = current_bytes

            progress = (completed_segs / total_segs * 100) if total_segs > 0 else 0.0

            if self.progress_callback:
                self.progress_callback({
                    'downloaded_bytes': current_bytes,
                    'file_size': current_bytes,  # Dynamic size estimation
                    'progress': progress,
                    'speed': current_speed
                })

    def _check_completion(self):
        """Check if all segments are downloaded and stitch them"""
        with self.lock:
            if not self.segments or self.state != DownloadState.DOWNLOADING:
                return
            all_done = all(s.downloaded for s in self.segments)

        if all_done:
            self._stitch_segments()

    def _stitch_segments(self):
        """Stitch TS segments into the target output file"""
        try:
            self.stop_event.set()
            stitched_ts = os.path.join(self.temp_dir, "stitched.ts")
            with open(stitched_ts, "wb") as outfile:
                for seg in sorted(self.segments, key=lambda s: s.index):
                    if os.path.exists(seg.file_path):
                        with open(seg.file_path, "rb") as infile:
                            shutil.copyfileobj(infile, outfile)

            out_dir = os.path.dirname(self.output_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            # Check if ffmpeg is available to remux TS to MP4
            ffmpeg_path = shutil.which("ffmpeg")
            moved = False
            if ffmpeg_path and self.output_file.lower().endswith(".mp4"):
                cmd = [
                    ffmpeg_path, "-y", "-i", stitched_ts,
                    "-c", "copy", "-bsf:a", "aac_adtstoasc",
                    self.output_file
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0 and os.path.exists(self.output_file):
                    moved = True

            if not moved:
                # Atomic replace with retries for raw stitched TS
                for attempt in range(5):
                    try:
                        os.replace(stitched_ts, self.output_file)
                        moved = True
                        break
                    except Exception:
                        time.sleep(0.2)
                if not moved and os.path.exists(stitched_ts):
                    shutil.copy2(stitched_ts, self.output_file)

            if os.path.exists(self.output_file):
                self.file_size = os.path.getsize(self.output_file)
                self.downloaded_bytes = self.file_size

            # Clean up temp dir
            shutil.rmtree(self.temp_dir, ignore_errors=True)

            self.state = DownloadState.DONE
            self._emit_event('download_complete', {
                'file_size': self.file_size,
                'downloaded_bytes': self.downloaded_bytes,
                'output_file': self.output_file
            })

        except Exception as e:
            self.state = DownloadState.ERROR
            self.stop_event.set()
            self._emit_event('error', {'message': f'Failed to stitch HLS segments: {str(e)}'})

    def pause_download(self):
        """Pause download"""
        if self.state == DownloadState.DOWNLOADING:
            self.state = DownloadState.PAUSED
            self.stop_event.set()
            self._emit_event('download_paused', {})

    def resume_download(self) -> bool:
        """Resume download"""
        if self.state == DownloadState.PAUSED:
            self.stop_event.clear()
            return self.start_download()
        return False

    def stop_download(self):
        """Stop download"""
        if self.state in [DownloadState.DOWNLOADING, DownloadState.PAUSED]:
            self.state = DownloadState.STOPPED
            self.stop_event.set()
            self._emit_event('download_stopped', {})

    def cleanup(self):
        """Clean up temporary segment files"""
        self.stop_download()
        if self.session:
            self.session.close()
            self.session = None
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def set_event_callback(self, callback: Callable):
        """Set callback for events"""
        self.event_callback = callback

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit download event"""
        if self.event_callback:
            event = DownloadEvent(event_type=event_type, data=data)
            self.event_callback(event)
