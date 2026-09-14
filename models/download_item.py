import os
import time
import uuid
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

from utils.download_engine import DownloadEngine
from utils.hls_engine import HLSEngine


class DownloadItem(QObject):
    """Manages one download using custom download engine based on FDM architecture."""
    progressChanged = pyqtSignal(int, int, int, float, int)  # downloaded, total, percent, speed, eta
    statusChanged = pyqtSignal(str)  # status string
    finished = pyqtSignal(object)    # self

    STATUS_PENDING = "Pending"
    STATUS_DOWNLOADING = "Downloading"
    STATUS_PAUSED = "Paused"
    STATUS_COMPLETED = "Completed"
    STATUS_ERROR = "Error"
    STATUS_STOPPED = "Stopped"

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, url: str, save_path: str, speed_limit: int = 0, parent=None, 
                 downloaded_bytes: int = 0, total_bytes: int = -1, status: str = STATUS_PENDING,
                 download_id: str = None):
        super().__init__(parent)
        self.download_id = download_id or str(uuid.uuid4())
        self.url = url
        dir_name = os.path.dirname(save_path)
        file_name = os.path.basename(save_path)
        from utils.helpers import sanitize_filename
        clean_file_name = sanitize_filename(file_name)
        self.save_path = os.path.join(dir_name, clean_file_name) if dir_name else clean_file_name
        self.speed_limit = speed_limit
        self.status = status
        self.downloaded_bytes = downloaded_bytes
        self.total_bytes = total_bytes
        self.current_speed = 0
        self.error_message = ""
        
        self.last_downloaded = downloaded_bytes
        self.last_time = time.time()
        
        # Additional download parameters
        self.referrer = ""
        self.cookies = ""
        self.user_agent = self.USER_AGENT
        self.post_data = ""
        self.document_url = ""
        
        # Initialize custom download engine based on URL type (HLS vs Direct File)
        if self._is_hls_url(url):
            self.download_engine = HLSEngine()
        else:
            self.download_engine = DownloadEngine()

        self.download_engine.set_event_callback(self._on_download_event)
        self.download_engine.set_progress_callback(self._on_download_progress)

    @staticmethod
    def _is_hls_url(url: str) -> bool:
        """Check if URL points to an HLS m3u8 playlist"""
        if not url:
            return False
        clean_url = url.split('?')[0].lower()
        return clean_url.endswith('.m3u8') or '.m3u8' in url.lower()

    def _configure_engine(self):
        """Configure download engine with current parameters."""
        if not self.download_engine:
            return
            
        self.download_engine.user_agent = self.user_agent
        self.download_engine.speed_limit = self.speed_limit * 1024  # Convert KB/s to bytes/s
        
        headers = {}
        if self.referrer:
            headers['Referer'] = self.referrer
        if self.cookies:
            headers['Cookie'] = self.cookies
        self.download_engine.headers = headers

    def _on_download_event(self, event):
        """Handle download events from the engine."""
        if event.event_type == 'download_started':
            self.status = self.STATUS_DOWNLOADING
            self.statusChanged.emit(self.status)
            
        elif event.event_type == 'download_complete':
            self.status = self.STATUS_COMPLETED
            self.current_speed = 0
            out_file = event.data.get('output_file') or self.save_path
            if os.path.exists(out_file):
                self.save_path = out_file
                real_size = os.path.getsize(out_file)
                self.downloaded_bytes = real_size
                self.total_bytes = real_size
            elif os.path.exists(self.save_path):
                real_size = os.path.getsize(self.save_path)
                self.downloaded_bytes = real_size
                self.total_bytes = real_size
            elif self.download_engine:
                self.downloaded_bytes = self.download_engine.downloaded_bytes
                self.total_bytes = self.download_engine.file_size or self.downloaded_bytes

            if self.parent() and hasattr(self.parent(), 'file_monitor'):
                self.parent().file_monitor.register_download_file(self.save_path, self.download_id)
            self.statusChanged.emit(self.status)
            self.emit_progress()
            self.finished.emit(self)
            
        elif event.event_type == 'download_paused':
            self.status = self.STATUS_PAUSED
            self.current_speed = 0
            self.statusChanged.emit(self.status)
            
        elif event.event_type == 'download_stopped':
            self.status = self.STATUS_STOPPED
            self.current_speed = 0
            self.statusChanged.emit(self.status)
            
        elif event.event_type == 'error':
            self.status = self.STATUS_ERROR
            self.current_speed = 0
            self.error_message = event.data.get('message', 'Unknown error')
            if self.download_engine:
                try:
                    self.download_engine.stop_download()
                except Exception:
                    pass
            self.statusChanged.emit(self.status)
            self.finished.emit(self)
            
        elif event.event_type == 'section_done':
            if self.status == self.STATUS_ERROR:
                return
            if self.download_engine:
                self.downloaded_bytes = self.download_engine.downloaded_bytes
                if self.download_engine.file_size > 0:
                    self.total_bytes = self.download_engine.file_size
            self.emit_progress()

    def _on_download_progress(self, progress_data):
        """Handle progress updates from the engine."""
        if self.status == self.STATUS_ERROR:
            return
        self.downloaded_bytes = progress_data['downloaded_bytes']
        if progress_data.get('file_size', 0) > 0:
            self.total_bytes = progress_data['file_size']
        self.current_speed = progress_data.get('speed', 0)
        self.emit_progress()

    def emit_progress(self):
        """Emit progressChanged signal with current file size and total bytes."""
        percent = -1
        if self.status == self.STATUS_COMPLETED:
            percent = 100
        elif self.total_bytes > 0:
            percent = min(100, max(0, int(self.downloaded_bytes * 100 / self.total_bytes)))
            if self.downloaded_bytes >= self.total_bytes:
                percent = 100
        
        # Calculate ETA
        eta = -1
        if self.status == self.STATUS_COMPLETED:
            eta = 0
        elif self.current_speed > 0 and self.total_bytes > 0:
            remaining = max(0, self.total_bytes - self.downloaded_bytes)
            eta = int(remaining / self.current_speed)
        
        self.progressChanged.emit(self.downloaded_bytes, self.total_bytes, percent, self.current_speed, eta)

    def start(self):
        """Start or resume download using custom download engine."""
        if self.status in (self.STATUS_COMPLETED, self.STATUS_DOWNLOADING):
            return
            
        self._configure_engine()
        
        if self.download_engine.state == self.download_engine.state.PAUSED:
            if self.download_engine.resume_download():
                self.status = self.STATUS_DOWNLOADING
                self.statusChanged.emit(self.status)
                return
        
        # Initialize and start download
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        if self.download_engine.initialize_download(self.url, self.save_path):
            self.total_bytes = self.download_engine.file_size
            self.downloaded_bytes = self.download_engine.downloaded_bytes
            if hasattr(self.download_engine, 'output_file') and self.download_engine.output_file:
                self.save_path = self.download_engine.output_file
            if self.download_engine.start_download():
                self.status = self.STATUS_DOWNLOADING
                self.statusChanged.emit(self.status)
            else:
                self.status = self.STATUS_ERROR
                self.error_message = "Failed to start download"
                self.statusChanged.emit(self.status)
        else:
            self.status = self.STATUS_ERROR
            self.error_message = "Failed to initialize download"
            self.statusChanged.emit(self.status)

    def pause(self):
        """Pause download using custom engine."""
        if self.status != self.STATUS_DOWNLOADING:
            return
        if self.download_engine:
            self.download_engine.pause_download()
        self.status = self.STATUS_PAUSED
        self.statusChanged.emit(self.status)

    def stop(self):
        """Stop download using custom engine."""
        if self.download_engine:
            self.download_engine.stop_download()
        self.status = self.STATUS_STOPPED
        self.statusChanged.emit(self.status)

    def remove(self):
        """Clean up and remove files."""
        if self.download_engine:
            self.download_engine.cleanup()
            if hasattr(self.download_engine, 'temp_file') and self.download_engine.temp_file and os.path.exists(self.download_engine.temp_file):
                try:
                    os.remove(self.download_engine.temp_file)
                except Exception:
                    pass
        
        if os.path.exists(self.save_path):
            try:
                os.remove(self.save_path)
            except Exception:
                pass
        self.deleteLater()

    def get_speed_kbps(self):
        return self.current_speed / 1024.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert download item to dictionary for persistence."""
        return {
            'download_id': self.download_id,
            'url': self.url,
            'save_path': self.save_path,
            'speed_limit': self.speed_limit,
            'status': self.status,
            'downloaded_bytes': self.downloaded_bytes,
            'total_bytes': self.total_bytes,
            'error_message': self.error_message,
            'referrer': self.referrer,
            'cookies': self.cookies,
            'user_agent': self.user_agent,
            'post_data': self.post_data,
            'document_url': self.document_url
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'DownloadItem':
        """Create download item from dictionary."""
        status = data.get('status', cls.STATUS_PENDING)
        
        if status == cls.STATUS_DOWNLOADING:
            status = cls.STATUS_PAUSED
        
        item = cls(
            download_id=data.get('download_id'),
            url=data.get('url', ''),
            save_path=data.get('save_path', ''),
            speed_limit=data.get('speed_limit', 0),
            parent=parent,
            downloaded_bytes=data.get('downloaded_bytes', 0),
            total_bytes=data.get('total_bytes', -1),
            status=status
        )
        
        item.referrer = data.get('referrer', '')
        item.cookies = data.get('cookies', '')
        item.user_agent = data.get('user_agent', cls.USER_AGENT)
        item.post_data = data.get('post_data', '')
        item.document_url = data.get('document_url', '')
        
        return item
