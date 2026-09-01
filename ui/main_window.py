"""
Main Window for Roxy Download Manager
"""
import os
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QStandardPaths, QUrl, QSize
from PyQt6.QtGui import QAction, QIcon, QDesktopServices
from PyQt6.QtWidgets import QStyle
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableView, QHeaderView,
    QToolBar, QStatusBar, QAbstractItemView, QSizePolicy, QDialog
)
from utils.constants import DARK_QSS, MAIN_API_PORT, APP_NAME
from utils.helpers import force_window_to_foreground
from utils.persistence import PersistenceManager
from utils.file_monitor import DownloadFileMonitor
from models import DownloadItem, DownloadTableModel, ProgressBarDelegate
from ui.title_bar import TitleBar
from ui.custom_table_view import CustomTableView
from ui.add_url_dialog import AddUrlDialog
from server import RoxyAPIServer


class MainWindow(QMainWindow):
    # Signal for download requests from HTTP API
    download_requested = pyqtSignal(str, str)  # url, filename
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(DARK_QSS)
        self.resize(1100, 650)
        self.setWindowTitle(APP_NAME)
        
        # Connect the download signal to the handler
        self.download_requested.connect(self.add_download_from_api)

        self.title_bar = TitleBar(self)
        self.setMenuWidget(self.title_bar)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        self.add_action = QAction("Add URL", self)
        self.add_action.triggered.connect(self.add_download)
        toolbar.addAction(self.add_action)

        self.pause_action = QAction("Pause", self)
        self.pause_action.triggered.connect(self.pause_selected)
        toolbar.addAction(self.pause_action)

        self.resume_action = QAction("Resume", self)
        self.resume_action.triggered.connect(self.resume_selected)
        toolbar.addAction(self.resume_action)

        self.remove_action = QAction("Remove", self)
        self.remove_action.triggered.connect(self.remove_selected)
        toolbar.addAction(self.remove_action)

        toolbar.addSeparator()

        self.start_all_action = QAction("Start All", self)
        self.start_all_action.triggered.connect(self.start_all)
        toolbar.addAction(self.start_all_action)

        self.stop_all_action = QAction("Stop All", self)
        self.stop_all_action.triggered.connect(self.stop_all)
        toolbar.addAction(self.stop_all_action)

        self.table = CustomTableView()
        self.model = DownloadTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 100)

        self.table.setItemDelegateForColumn(3, ProgressBarDelegate(self.table))

        main_layout.addWidget(self.table)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.moving = False
        self.offset = QPoint()

        # Start API server for Chrome extension
        self.api_server = RoxyAPIServer(port=MAIN_API_PORT, main_window=self)
        self.api_server.start()
        
        # Initialize persistence manager
        self.persistence = PersistenceManager()
        
        # Initialize file monitor for tracking download files
        self.file_monitor = DownloadFileMonitor(
            on_file_deleted=self._on_file_deleted,
            on_file_created=self._on_file_created,
            on_file_moved=self._on_file_moved
        )
        self.file_monitor.start()
        
        # Load saved downloads on startup
        self._load_saved_downloads()

    # ---- Action button management ----
    def _setup_action_button_for_row(self, row, dl):
        btn = QPushButton()
        btn.setFixedWidth(70)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 2px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { background-color: #2a2a2a; }
        """)
        self.table.setIndexWidget(self.model.index(row, 0), btn)
        self._update_action_button(btn, dl)
        dl.statusChanged.connect(lambda status, b=btn, d=dl: self._update_action_button(b, d))
        btn.clicked.connect(lambda checked, d=dl: self._on_action_button_clicked(d))

    def _update_action_button(self, btn, dl):
        """Update button text/icon based on download status."""
        # Check if button still exists (might have been deleted)
        try:
            if not btn or not hasattr(btn, 'setIcon'):
                return
        except:
            return
        
        if dl.status == DownloadItem.STATUS_COMPLETED:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
            btn.setIcon(icon)
            btn.setText("")
            btn.setToolTip("Open containing folder")
            if not os.path.exists(dl.save_path):
                btn.setEnabled(False)
                btn.setToolTip("File missing")
            else:
                btn.setEnabled(True)
        elif dl.status == DownloadItem.STATUS_DOWNLOADING:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            btn.setIcon(icon)
            btn.setText("")
            btn.setToolTip("Pause download")
            btn.setEnabled(True)
        elif dl.status == DownloadItem.STATUS_PAUSED:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            btn.setIcon(icon)
            btn.setText("")
            btn.setToolTip("Resume download")
            btn.setEnabled(True)
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            btn.setIcon(icon)
            btn.setText("")
            btn.setToolTip("Start download")
            btn.setEnabled(True)

    def _on_action_button_clicked(self, dl):
        if dl.status == DownloadItem.STATUS_COMPLETED:
            if os.path.exists(dl.save_path):
                folder = os.path.dirname(dl.save_path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        elif dl.status == DownloadItem.STATUS_DOWNLOADING:
            dl.pause()
        elif dl.status == DownloadItem.STATUS_PAUSED:
            dl.start()
        else:
            dl.start()

    # ---- Existing methods ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.moving = True
            self.offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.moving:
            self.move(event.globalPosition().toPoint() - self.offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.moving = False
        super().mouseReleaseEvent(event)

    def add_download(self):
        dialog = AddUrlDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.url
            save_path = dialog.selected_path
            speed_limit = dialog.speed_limit
            dl = DownloadItem(url, save_path, speed_limit, self)
            self.model.add_download(dl)
            row = self.model.rowCount() - 1
            self._setup_action_button_for_row(row, dl)
            # Register with file monitor
            self.file_monitor.register_download_file(dl.save_path, dl.download_id)
            dl.start()
            self.status_bar.showMessage(f"Added download: {os.path.basename(save_path)}", 3000)

    def add_download_from_api(self, url: str, filename: str = None):
        """Add download from API call with default settings."""
        print(f"🔍 DEBUG: add_download_from_api called with URL: {url}")
        print(f"🔍 DEBUG: Provided filename: {filename}")
        
        # Force window to foreground using Windows API without changing flags
        force_window_to_foreground(int(self.winId()))
        
        # Use Qt methods to bring to front
        self.show()
        self.raise_()
        self.activateWindow()
        
        downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not downloads_dir or not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")
        
        # Use provided filename if available, otherwise simple fallback from URL
        if filename and filename.strip():
            print(f"🔍 DEBUG: Using provided filename: {filename}")
            save_path = os.path.join(downloads_dir, filename)
        else:
            print(f"🔍 DEBUG: No filename provided, using simple URL fallback")
            simple_filename = os.path.basename(url.split('?')[0]) or "download"
            save_path = os.path.join(downloads_dir, simple_filename)
        
        print(f"🔍 DEBUG: Creating download item with save path: {save_path}")
        
        dl = DownloadItem(url, save_path, 0, self)
        self.model.add_download(dl)
        row = self.model.rowCount() - 1
        self._setup_action_button_for_row(row, dl)
        # Register with file monitor
        self.file_monitor.register_download_file(dl.save_path, dl.download_id)
        dl.start()
        
        print(f"🔍 DEBUG: Download started for URL: {url}")
        self.status_bar.showMessage(f"Added download from extension: {os.path.basename(save_path)}", 3000)

    def selected_row(self):
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            return indexes[0].row()
        return -1

    def pause_selected(self):
        row = self.selected_row()
        if row >= 0:
            dl = self.model.get_download(row)
            if dl:
                dl.pause()
                self.status_bar.showMessage(f"Paused: {os.path.basename(dl.save_path)}", 3000)

    def resume_selected(self):
        row = self.selected_row()
        if row >= 0:
            dl = self.model.get_download(row)
            if dl and dl.status != DownloadItem.STATUS_DOWNLOADING:
                dl.start()
                self.status_bar.showMessage(f"Resumed: {os.path.basename(dl.save_path)}", 3000)

    def remove_selected(self):
        row = self.selected_row()
        if row >= 0:
            dl = self.model.get_download(row)
            if dl:
                # Disconnect signals to prevent updates after removal
                try:
                    dl.statusChanged.disconnect()
                except:
                    pass
                # Unregister from file monitor
                self.file_monitor.unregister_download_file(dl.save_path)
                self.model.remove_download(row)
                self.status_bar.showMessage("Removed download", 3000)

    def start_all(self):
        for dl in self.model.downloads:
            if dl.status in [DownloadItem.STATUS_PAUSED, DownloadItem.STATUS_PENDING, DownloadItem.STATUS_STOPPED]:
                dl.start()
        self.status_bar.showMessage("Starting all downloads", 3000)

    def stop_all(self):
        for dl in self.model.downloads:
            if dl.status == DownloadItem.STATUS_DOWNLOADING:
                dl.pause()
        self.status_bar.showMessage("Paused all downloads", 3000)

    def closeEvent(self, event):
        # Save download state before closing
        self._save_downloads()
        
        for dl in self.model.downloads:
            dl.stop()
        # Stop API server
        if hasattr(self, 'api_server'):
            self.api_server.stop()
        # Stop file monitor
        if hasattr(self, 'file_monitor'):
            self.file_monitor.stop()
        # Release single instance lock
        if hasattr(self, 'single_instance'):
            self.single_instance.release_lock()
        event.accept()
    
    def _save_downloads(self):
        """Save current download state to disk."""
        try:
            downloads_data = []
            for dl in self.model.downloads:
                # Save all downloads including completed ones
                # Completed downloads will be restored if files still exist
                downloads_data.append(dl.to_dict())
            
            if downloads_data:
                self.persistence.save_downloads(downloads_data)
            else:
                # If no downloads, clear the state file
                self.persistence.clear_state()
        except Exception as e:
            print(f"Error saving downloads: {e}")
    
    def _load_saved_downloads(self):
        """Load saved download state from disk."""
        try:
            saved_downloads = self.persistence.load_downloads()
            restored_count = 0
            
            for download_data in saved_downloads:
                # Restore download from saved state
                dl = DownloadItem.from_dict(download_data, parent=self)
                
                # For completed downloads, only restore if file still exists
                if dl.status == DownloadItem.STATUS_COMPLETED:
                    if not os.path.exists(dl.save_path):
                        # File was deleted, skip this download
                        print(f"Skipping completed download - file not found: {dl.save_path}")
                        continue
                    # File exists, restore as completed
                    dl.downloaded_bytes = os.path.getsize(dl.save_path)
                    if dl.total_bytes == -1:
                        dl.total_bytes = dl.downloaded_bytes
                else:
                    # For incomplete downloads, check if file still exists and has content
                    if os.path.exists(dl.save_path):
                        # Update downloaded_bytes to actual file size
                        try:
                            actual_size = os.path.getsize(dl.save_path)
                            dl.downloaded_bytes = actual_size
                            # Enable resume if file has content
                            if actual_size > 0:
                                dl._resume = True
                        except:
                            dl.downloaded_bytes = 0
                            dl._resume = False
                    else:
                        dl.downloaded_bytes = 0
                        dl._resume = False
                
                # Add to model
                self.model.add_download(dl)
                row = self.model.rowCount() - 1
                self._setup_action_button_for_row(row, dl)
                restored_count += 1
                
                # Register with file monitor
                self.file_monitor.register_download_file(dl.save_path, dl.download_id)
                
                # Update status to reflect current state
                if dl.status == DownloadItem.STATUS_DOWNLOADING:
                    # Change downloading status to paused on restore
                    dl.status = DownloadItem.STATUS_PAUSED
                    dl.statusChanged.emit(dl.status)
                
            if restored_count > 0:
                self.status_bar.showMessage(f"Restored {restored_count} downloads", 3000)
                
        except Exception as e:
            print(f"Error loading saved downloads: {e}")
    
    def _on_file_deleted(self, download_id: str):
        """Handle file deletion event from file monitor."""
        # Find and remove the download with matching ID
        for i, dl in enumerate(self.model.downloads):
            if dl.download_id == download_id:
                print(f"Removing download {download_id} due to file deletion")
                # Disconnect signals to prevent updates after removal
                try:
                    dl.statusChanged.disconnect()
                except:
                    pass
                # Unregister from file monitor
                self.file_monitor.unregister_download_file(dl.save_path)
                self.model.remove_download(i)
                self.status_bar.showMessage("Download removed - file deleted", 3000)
                break
    
    def _on_file_created(self, file_path: str):
        """Handle file creation event from file monitor."""
        # Currently not used, but could be used to detect new downloads
        pass
    
    def _on_file_moved(self, download_id: str, new_path: str):
        """Handle file move event from file monitor."""
        # Find and update the download with matching ID
        for dl in self.model.downloads:
            if dl.download_id == download_id:
                print(f"Updating download {download_id} path to {new_path}")
                # Unregister old path and register new path
                self.file_monitor.unregister_download_file(dl.save_path)
                dl.save_path = new_path
                self.file_monitor.register_download_file(dl.save_path, dl.download_id)
                # Update button state since file location changed
                if dl.status == DownloadItem.STATUS_COMPLETED:
                    dl.statusChanged.emit(dl.status)
                self.status_bar.showMessage("Download file moved", 3000)
                break
