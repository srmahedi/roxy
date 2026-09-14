"""
File system monitor for tracking download files in real-time
"""
import os
import threading
from typing import Callable, Dict, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileDeletedEvent, FileCreatedEvent, FileMovedEvent


from PyQt6.QtCore import QObject, pyqtSignal


class FileMonitorSignals(QObject):
    file_deleted = pyqtSignal(str)
    file_created = pyqtSignal(str)
    file_moved = pyqtSignal(str, str)


class DownloadFileMonitor(FileSystemEventHandler):
    """Monitors download directories for file changes."""
    
    def __init__(self, on_file_deleted: Callable[[str], None], 
                 on_file_created: Callable[[str], None],
                 on_file_moved: Callable[[str, str], None]):
        super().__init__()
        self.signals = FileMonitorSignals()
        if on_file_deleted:
            self.signals.file_deleted.connect(on_file_deleted)
        if on_file_created:
            self.signals.file_created.connect(on_file_created)
        if on_file_moved:
            self.signals.file_moved.connect(on_file_moved)
        self.monitored_directories: Set[str] = set()
        self.observer = Observer()
        self.file_to_download_map: Dict[str, str] = {}  # Maps file paths to download IDs
        
    def add_directory(self, directory: str):
        """Add a directory to monitor."""
        if directory not in self.monitored_directories and os.path.exists(directory):
            try:
                self.observer.schedule(self, directory, recursive=False)
                self.monitored_directories.add(directory)
                print(f"Now monitoring directory: {directory}")
            except Exception as e:
                print(f"Error monitoring directory {directory}: {e}")
    
    def remove_directory(self, directory: str):
        """Remove a directory from monitoring."""
        if directory in self.monitored_directories:
            try:
                # Note: watchdog doesn't have direct unschedule for paths, 
                # so we'd need to track and recreate the observer
                self.monitored_directories.remove(directory)
                print(f"Stopped monitoring directory: {directory}")
            except Exception as e:
                print(f"Error stopping monitoring for {directory}: {e}")
    
    def start(self):
        """Start the file system monitor."""
        if not self.observer.is_alive():
            self.observer.start()
            print("File system monitor started")
    
    def stop(self):
        """Stop the file system monitor."""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            print("File system monitor stopped")
    
    def register_download_file(self, file_path: str, download_id):
        """Register a download file for tracking."""
        # Convert download_id to string if it's an integer (for active downloads)
        download_id_str = str(download_id)
        self.file_to_download_map[file_path] = download_id_str
        # Also monitor the directory if not already monitored
        directory = os.path.dirname(file_path)
        self.add_directory(directory)
    
    def unregister_download_file(self, file_path: str):
        """Unregister a download file from tracking."""
        if file_path in self.file_to_download_map:
            del self.file_to_download_map[file_path]
    
    def on_deleted(self, event):
        """Handle file deletion events."""
        if not event.is_directory:
            file_path = event.src_path
            if file_path in self.file_to_download_map:
                download_id = self.file_to_download_map[file_path]
                print(f"Download file deleted: {file_path} (ID: {download_id})")
                self.signals.file_deleted.emit(download_id)
                self.unregister_download_file(file_path)
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = event.src_path
            print(f"File created: {file_path}")
            self.signals.file_created.emit(file_path)
    
    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory:
            src_path = event.src_path
            dest_path = event.dest_path
            print(f"File moved from {src_path} to {dest_path}")
            if src_path in self.file_to_download_map:
                download_id = self.file_to_download_map[src_path]
                self.signals.file_moved.emit(download_id, dest_path)
                # Update the mapping
                del self.file_to_download_map[src_path]
                self.file_to_download_map[dest_path] = download_id