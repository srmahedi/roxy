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
from utils.helpers import force_window_to_foreground, extract_filename_from_url, get_unique_filepath
from utils.persistence import PersistenceManager
from utils.file_monitor import DownloadFileMonitor
from models import DownloadItem, DownloadTableModel, ProgressBarDelegate
from ui.title_bar import TitleBar
from ui.custom_table_view import CustomTableView
from ui.add_url_dialog import AddUrlDialog
from ui.duplicate_dialog import DuplicateDownloadDialog
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

        self.action_buttons = {}

        self.table = CustomTableView()
        self.model = DownloadTableModel(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.model.rowsInserted.connect(self._refresh_action_buttons)
        self.model.rowsRemoved.connect(self._refresh_action_buttons)
        self.model.modelReset.connect(self._refresh_action_buttons)

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
    def _create_action_button_for_item(self, dl):
        if dl in self.action_buttons:
            return self.action_buttons[dl]
        
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
        self._update_action_button(btn, dl)
        dl.statusChanged.connect(lambda status, b=btn, d=dl: self._update_action_button(b, d))
        btn.clicked.connect(lambda checked, d=dl: self._on_action_button_clicked(d))
        self.action_buttons[dl] = btn
        return btn

    def _refresh_action_buttons(self):
        """Re-bind index widgets for all rows in table model."""
        current_dls = set(self.model.downloads)
        for dl in list(self.action_buttons.keys()):
            if dl not in current_dls:
                btn = self.action_buttons.pop(dl)
                btn.deleteLater()

        for row, dl in enumerate(self.model.downloads):
            btn = self._create_action_button_for_item(dl)
            self._update_action_button(btn, dl)
            self.table.setIndexWidget(self.model.index(row, 0), btn)

    def _update_action_button(self, btn, dl):
        """Update button text/icon based on download status."""
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
                # Select the file in File Explorer instead of just opening the folder
                import subprocess
                # Convert path to proper Windows format
                win_path = os.path.normpath(dl.save_path)
                print(f"DEBUG: Opening explorer for file: {win_path}")
                result = subprocess.run(['explorer', '/select,', win_path], capture_output=True)
                print(f"DEBUG: Explorer command result: {result.returncode}")
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

    def _check_and_resolve_duplicate(self, url: str, save_path: str) -> str:
        """
        Checks if a file or URL is a duplicate. If duplicate is found, presents
        DuplicateDownloadDialog to the user.
        Returns final save_path string, or None if download is cancelled.
        """
        norm_path = os.path.normpath(save_path).lower()
        is_file_dup = os.path.exists(save_path)
        
        # Check if URL or save path is already in existing download table items
        existing_path_row = -1
        existing_url_row = -1
        for row, dl in enumerate(self.model.downloads):
            if os.path.normpath(dl.save_path).lower() == norm_path:
                existing_path_row = row
            if dl.url == url:
                existing_url_row = row
        
        is_url_dup = existing_url_row >= 0
        is_table_path_dup = existing_path_row >= 0

        # If no duplicate detected at all, return original save_path
        if not (is_file_dup or is_url_dup or is_table_path_dup):
            return save_path

        filename = os.path.basename(save_path)
        dup_dialog = DuplicateDownloadDialog(
            self,
            filename=filename,
            url=url,
            save_path=save_path,
            is_file_duplicate=is_file_dup or is_table_path_dup,
            is_url_duplicate=is_url_dup
        )

        if dup_dialog.exec() == QDialog.DialogCode.Accepted:
            if dup_dialog.action == DuplicateDownloadDialog.ACTION_RENAME:
                existing_paths = [d.save_path for d in self.model.downloads]
                new_path = get_unique_filepath(save_path, existing_paths=existing_paths)
                return new_path
            elif dup_dialog.action == DuplicateDownloadDialog.ACTION_OVERWRITE:
                # Remove ONLY table items matching the exact save_path being overwritten
                # (Leave numbered files like filename (1).ext untouched in the table)
                if existing_path_row >= 0:
                    old_dl = self.model.get_download(existing_path_row)
                    if old_dl:
                        old_dl.stop()
                        try:
                            old_dl.statusChanged.disconnect()
                        except:
                            pass
                        self.file_monitor.unregister_download_file(old_dl.save_path)
                        self.model.remove_download(existing_path_row)
                
                # Delete target file on disk if it exists so engine starts fresh
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except Exception as e:
                        print(f"DEBUG: Could not delete existing file for overwrite: {e}")
                
                return save_path

        # If cancelled or rejected
        return None

    def add_download(self):
        dialog = AddUrlDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.url
            save_path = dialog.selected_path
            speed_limit = dialog.speed_limit
            
            resolved_path = self._check_and_resolve_duplicate(url, save_path)
            if not resolved_path:
                self.status_bar.showMessage("Download cancelled", 3000)
                return

            dl = DownloadItem(url, resolved_path, speed_limit, self)
            self.model.add_download(dl)
            self._refresh_action_buttons()
            # Register with file monitor
            self.file_monitor.register_download_file(dl.save_path, dl.download_id)
            dl.start()
            self._save_downloads()
            self.status_bar.showMessage(f"Added download: {os.path.basename(resolved_path)}", 3000)

    def add_download_from_api(self, url: str, filename: str = None, additional_info: dict = None):
        """Add download from API call with additional parameters."""
        print(f"DEBUG: add_download_from_api called with URL: {url}")
        print(f"DEBUG: Provided filename: {filename}")
        
        # Check for pending download info from API server
        if additional_info is None and hasattr(self, '_pending_download_info'):
            additional_info = self._pending_download_info
            delattr(self, '_pending_download_info')
        
        print(f"DEBUG: Additional info: {additional_info}")
        
        # Force window to foreground using Windows API without changing flags
        force_window_to_foreground(int(self.winId()))
        
        # Use Qt methods to bring to front
        self.show()
        self.raise_()
        self.activateWindow()
        
        downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not downloads_dir or not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")
        
        # Pull cookies/referrer early so the filename probe can authenticate
        probe_cookies = additional_info.get('cookies', '') if additional_info else ''
        probe_referrer = additional_info.get('referrer', '') if additional_info else ''

        # Use improved filename extraction function (pass auth headers for services like GDrive)
        extracted_filename = extract_filename_from_url(
            url, filename,
            cookies=probe_cookies or None,
            referrer=probe_referrer or None,
        )
        print(f"DEBUG: Extracted filename: {extracted_filename}")
        
        save_path = os.path.join(downloads_dir, extracted_filename)
        
        resolved_path = self._check_and_resolve_duplicate(url, save_path)
        if not resolved_path:
            self.status_bar.showMessage("Extension download cancelled (duplicate skipped)", 3000)
            return

        print(f"DEBUG: Creating download item with save path: {resolved_path}")
        
        dl = DownloadItem(url, resolved_path, 0, self)
        
        # Add additional information if provided
        if additional_info:
            if additional_info.get('referrer'):
                dl.referrer = additional_info['referrer']
            if additional_info.get('cookies'):
                dl.cookies = additional_info['cookies']
            if additional_info.get('userAgent'):
                dl.user_agent = additional_info['userAgent']
            if additional_info.get('postData'):
                dl.post_data = additional_info['postData']
            if additional_info.get('documentUrl'):
                dl.document_url = additional_info['documentUrl']
        
        self.model.add_download(dl)
        self._refresh_action_buttons()
        # Register with file monitor
        self.file_monitor.register_download_file(dl.save_path, dl.download_id)
        dl.start()
        self._save_downloads()
        
        print(f"DEBUG: Download started for URL: {url}")
        self.status_bar.showMessage(f"Added download from extension: {os.path.basename(resolved_path)}", 3000)
    
    def update_settings(self, settings: dict):
        """Update settings from extension."""
        print(f"DEBUG: Updating settings: {settings}")
        # In a real implementation, this would update the application settings
        # For now, we'll just log it
        pass

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
                self._save_downloads()
                self.status_bar.showMessage(f"Paused: {os.path.basename(dl.save_path)}", 3000)

    def resume_selected(self):
        row = self.selected_row()
        if row >= 0:
            dl = self.model.get_download(row)
            if dl and dl.status != DownloadItem.STATUS_DOWNLOADING:
                dl.start()
                self._save_downloads()
                self.status_bar.showMessage(f"Resumed: {os.path.basename(dl.save_path)}", 3000)

    def remove_selected(self):
        row = self.selected_row()
        if row >= 0:
            dl = self.model.get_download(row)
            if dl:
                try:
                    dl.statusChanged.disconnect()
                except:
                    pass
                self.file_monitor.unregister_download_file(dl.save_path)
                self.model.remove_download(row)
                self._save_downloads()
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
                restored_count += 1
                
                # Register with file monitor
                self.file_monitor.register_download_file(dl.save_path, dl.download_id)
                
                # Update status to reflect current state
                if dl.status == DownloadItem.STATUS_DOWNLOADING:
                    # Change downloading status to paused on restore
                    dl.status = DownloadItem.STATUS_PAUSED
                    dl.statusChanged.emit(dl.status)
                
            self._refresh_action_buttons()
            if restored_count > 0:
                self.status_bar.showMessage(f"Restored {restored_count} downloads", 3000)
                
        except Exception as e:
            print(f"Error loading saved downloads: {e}")
    
    def _on_file_deleted(self, download_id: str):
        """Handle file deletion event from file monitor."""
        # Find the download with matching ID
        for i, dl in enumerate(self.model.downloads):
            if dl.download_id == download_id:
                # Do not delete item if download is actively downloading or pending
                if dl.status in (DownloadItem.STATUS_DOWNLOADING, DownloadItem.STATUS_PENDING):
                    print(f"Ignored file deletion event for active download {download_id}")
                    return
                # Check if temp file or save path still exists (e.g. during atomic replace)
                temp_file = getattr(dl.download_engine, 'temp_file', '') if dl.download_engine else ''
                if os.path.exists(dl.save_path) or (temp_file and os.path.exists(temp_file)):
                    print(f"Ignored file deletion event - file exists: {dl.save_path}")
                    return

                print(f"File deleted on disk for download {download_id}")
                btn = self.action_buttons.get(dl)
                if btn:
                    self._update_action_button(btn, dl)
                self.model.update_item(dl)
                self.status_bar.showMessage(f"File missing: {os.path.basename(dl.save_path)}", 3000)
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
                self.model.update_item(dl)
                btn = self.action_buttons.get(dl)
                if btn:
                    self._update_action_button(btn, dl)
                self._save_downloads()
                self.status_bar.showMessage("Download file moved", 3000)
                break
