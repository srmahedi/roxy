"""
Download Item model for managing individual downloads
"""
import os
import time
import subprocess
import re
import uuid
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QProcess


class DownloadItem(QObject):
    """Manages one download using curl subprocess."""
    progressChanged = pyqtSignal(int, int, int, float, int)  # downloaded, total, percent, speed, eta
    statusChanged = pyqtSignal(str)  # status string
    finished = pyqtSignal(object)    # self

    STATUS_PENDING = "Pending"
    STATUS_DOWNLOADING = "Downloading"
    STATUS_PAUSED = "Paused"
    STATUS_COMPLETED = "Completed"
    STATUS_ERROR = "Error"
    STATUS_STOPPED = "Stopped"

    def __init__(self, url: str, save_path: str, speed_limit: int = 0, parent=None, 
                 downloaded_bytes: int = 0, total_bytes: int = -1, status: str = STATUS_PENDING,
                 download_id: str = None):
        super().__init__(parent)
        self.download_id = download_id or str(uuid.uuid4())
        self.url = url
        self.save_path = save_path
        self.speed_limit = speed_limit
        self.process: Optional[QProcess] = None
        self.status = status
        self.downloaded_bytes = downloaded_bytes
        self.total_bytes = total_bytes
        self.last_downloaded = downloaded_bytes
        self.last_time = time.time()
        self.current_speed = 0
        self.error_message = ""
        self._resume = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_progress)
        self._timer.setInterval(1000)

        # Get total size for new downloads (only if not already set)
        if self.total_bytes == -1:
            self._get_total_size()
        
        # If we have downloaded bytes from a saved state, enable resume
        if self.downloaded_bytes > 0:
            self._resume = True

    def _get_total_size(self):
        """Get file size from Content-Length header via curl -I."""
        try:
            cmd = ["curl", "-sIL", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            headers = result.stdout
            matches = re.findall(r'[Cc]ontent-[Ll]ength:\s*(\d+)', headers)
            if matches:
                self.total_bytes = int(matches[-1])
        except Exception:
            pass

    def start(self):
        """Start or resume download."""
        if self.status == self.STATUS_COMPLETED:
            return
        if self.status == self.STATUS_DOWNLOADING:
            return

        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)

        args = [
            "curl",
            "-L",
            "-o", self.save_path,
            "--silent",
            "--show-error",
            "--fail",
        ]
        if self.speed_limit > 0:
            args.extend(["--limit-rate", f"{self.speed_limit}k"])
        if self.status == self.STATUS_PAUSED or self._resume:
            args.append("-C")
            args.append("-")
        args.append(self.url)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.finished.connect(self._on_process_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.status = self.STATUS_DOWNLOADING
        self.statusChanged.emit(self.status)
        self.last_time = time.time()
        self.last_downloaded = self.downloaded_bytes
        self.process.start("curl", args[1:])
        self._timer.start()

    def pause(self):
        """Pause download by terminating curl process."""
        if self.status != self.STATUS_DOWNLOADING:
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
        self._timer.stop()
        self.status = self.STATUS_PAUSED
        self.statusChanged.emit(self.status)
        if os.path.exists(self.save_path):
            self.downloaded_bytes = os.path.getsize(self.save_path)
        self._resume = True

    def stop(self):
        """Stop (not pause) the download."""
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
        self._timer.stop()
        self.status = self.STATUS_STOPPED
        self.statusChanged.emit(self.status)

    def remove(self):
        """Clean up and remove files."""
        self.stop()
        if os.path.exists(self.save_path):
            try:
                os.remove(self.save_path)
            except:
                pass
        self.deleteLater()

    def _poll_progress(self):
        """Called every second to update progress based on file size."""
        if self.status != self.STATUS_DOWNLOADING:
            return
        if not os.path.exists(self.save_path):
            return
        try:
            current_size = os.path.getsize(self.save_path)
        except OSError:
            return
        now = time.time()
        dt = now - self.last_time
        if dt <= 0:
            return
        speed = (current_size - self.last_downloaded) / dt
        self.current_speed = speed
        self.downloaded_bytes = current_size
        self.last_downloaded = current_size
        self.last_time = now

        if speed > 0 and self.total_bytes > 0:
            remaining = self.total_bytes - current_size
            eta = int(remaining / speed)
        else:
            eta = -1

        percent = -1
        if self.total_bytes > 0:
            percent = int(current_size * 100 / self.total_bytes)
        self.progressChanged.emit(current_size, self.total_bytes, percent, speed, eta)

    def _on_process_finished(self, exit_code, exit_status):
        self._timer.stop()
        if self.status == self.STATUS_PAUSED:
            return
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            if os.path.exists(self.save_path):
                self.downloaded_bytes = os.path.getsize(self.save_path)
                if self.total_bytes == -1:
                    self.total_bytes = self.downloaded_bytes
                # Register with file monitor when download completes
                if self.parent() and hasattr(self.parent(), 'file_monitor'):
                    self.parent().file_monitor.register_download_file(self.save_path, self.download_id)
            self.status = self.STATUS_COMPLETED
            self.statusChanged.emit(self.status)
            self.progressChanged.emit(self.downloaded_bytes, self.total_bytes, 100, 0, 0)
        else:
            if self.status != self.STATUS_PAUSED and self.status != self.STATUS_STOPPED:
                self.status = self.STATUS_ERROR
                self.error_message = self._read_error()
                self.statusChanged.emit(self.status)
                self.progressChanged.emit(self.downloaded_bytes, self.total_bytes, -1, 0, -1)
        self.finished.emit(self)

    def _on_process_error(self, error):
        if self.status != self.STATUS_PAUSED and self.status != self.STATUS_STOPPED:
            self.status = self.STATUS_ERROR
            self.error_message = f"Process error: {error}"
            self.statusChanged.emit(self.status)
            self._timer.stop()
            self.finished.emit(self)

    def _read_error(self):
        if self.process:
            output = bytes(self.process.readAllStandardError()).decode('utf-8', errors='ignore')
            return output.strip() or "Unknown error"
        return "Unknown error"

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
            'error_message': self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'DownloadItem':
        """Create download item from dictionary."""
        return cls(
            download_id=data.get('download_id'),
            url=data.get('url', ''),
            save_path=data.get('save_path', ''),
            speed_limit=data.get('speed_limit', 0),
            parent=parent,
            downloaded_bytes=data.get('downloaded_bytes', 0),
            total_bytes=data.get('total_bytes', -1),
            status=data.get('status', cls.STATUS_PENDING)
        )
