"""
Add URL Dialog for adding new downloads
"""
import os
from PyQt6.QtCore import QStandardPaths, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QDialogButtonBox, QMessageBox, QFileDialog, QLabel
)
from utils.constants import DARK_QSS
from utils.helpers import extract_filename_from_url
import requests


class URLValidatorThread(QThread):
    """Thread to validate URL accessibility"""
    validation_result = pyqtSignal(bool, str, int)  # success, message, file_size

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.head(self.url, headers=headers, allow_redirects=True, timeout=10)
            if response.status_code == 200 or response.status_code == 206:
                content_length = response.headers.get('content-length', '')
                file_size = int(content_length) if content_length.isdigit() else 0
                self.validation_result.emit(True, "URL is accessible", file_size)
            else:
                self.validation_result.emit(False, f"Server returned {response.status_code} {response.reason}", 0)
        except requests.exceptions.Timeout:
            self.validation_result.emit(False, "Connection timeout", 0)
        except requests.exceptions.ConnectionError:
            self.validation_result.emit(False, "Connection failed", 0)
        except Exception as e:
            self.validation_result.emit(False, f"Error: {str(e)}", 0)


class AddUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Download")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet(DARK_QSS)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        form.addRow("URL:", self.url_edit)

        # Add check URL button
        url_layout = QHBoxLayout()
        check_btn = QPushButton("Check URL")
        check_btn.setObjectName("check_btn")
        check_btn.clicked.connect(self.check_url)
        self.url_status_label = QLabel()
        self.url_status_label.setStyleSheet("color: #888; font-size: 11px;")
        url_layout.addWidget(check_btn)
        url_layout.addWidget(self.url_status_label)
        url_layout.addStretch()
        form.addRow("", url_layout)

        self.save_path_edit = QLineEdit()
        self.save_path_edit.setPlaceholderText("Select file location...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_save_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.save_path_edit)
        path_layout.addWidget(browse_btn)
        form.addRow("Save to:", path_layout)

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 100000)
        self.speed_limit_spin.setSuffix(" KB/s")
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        form.addRow("Speed limit:", self.speed_limit_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Default save location: OS Downloads folder
        self.downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not self.downloads_dir or not os.path.isdir(self.downloads_dir):
            self.downloads_dir = os.path.expanduser("~")
        self.save_path_edit.setText(self.downloads_dir)

        self.selected_path = None
        self.url = ""
        self.speed_limit = 0
        self.validator_thread = None
        self.url_valid = None  # None = not checked, True = valid, False = invalid
        self.check_timer = QTimer()
        self.check_timer.setSingleShot(True)
        self.check_timer.timeout.connect(self.check_url)
        self.url_edit.textChanged.connect(self.on_url_text_changed)
        self._disable_auto_check = False  # Flag to disable auto-check when setting URL programmatically

    def closeEvent(self, event):
        """Clean up validator thread when dialog is closed"""
        if self.validator_thread and self.validator_thread.isRunning():
            self.validator_thread.quit()
            self.validator_thread.wait(1000)  # Wait up to 1 second
        if self.check_timer:
            self.check_timer.stop()
        super().closeEvent(event)

    def on_url_text_changed(self):
        """Handle URL text changes - auto-check after user stops typing"""
        # Skip auto-check if disabled (when setting URL programmatically)
        if self._disable_auto_check:
            return

        # Cancel any pending check
        self.check_timer.stop()
        # Reset validation status when URL changes
        self.url_valid = None
        self.url_status_label.setText("")
        # Schedule auto-check after 500ms of no typing
        self.check_timer.start(500)

    def browse_save_path(self):
        url = self.url_edit.text().strip()
        default_name = ""
        if url:
            default_name = extract_filename_from_url(url)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            os.path.join(self.downloads_dir, default_name),
            "All Files (*)"
        )
        if file_path:
            self.save_path_edit.setText(file_path)

    def check_url(self):
        """Check if the URL is accessible"""
        url = self.url_edit.text().strip()
        if not url:
            # Silently return if URL is empty (don't show warning for auto-check on dialog open)
            return

        self.url_status_label.setText("Checking...")
        self.url_status_label.setStyleSheet("color: #888; font-size: 11px;")
        check_btn = self.findChild(QPushButton, "check_btn")
        if check_btn:
            check_btn.setEnabled(False)

        self.validator_thread = URLValidatorThread(url)
        self.validator_thread.validation_result.connect(self.on_validation_result)
        self.validator_thread.start()

    def on_validation_result(self, success, message, file_size):
        """Handle URL validation result"""
        if success:
            size_str = f" ({file_size / (1024*1024):.2f} MB)" if file_size > 0 else ""
            self.url_status_label.setText(f"✓ Valid{size_str}")
            self.url_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
            self.url_valid = True
        else:
            self.url_status_label.setText(f"✗ {message}")
            self.url_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
            self.url_valid = False

        # Re-enable check button
        check_btn = self.findChild(QPushButton, "check_btn")
        if check_btn:
            check_btn.setEnabled(True)

    def accept(self):
        url = self.url_edit.text().strip()
        path = self.save_path_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a URL.")
            return
        if not path:
            QMessageBox.warning(self, "Missing Save Path", "Please choose a save location.")
            return

        # If URL was checked and failed, show error and don't allow download
        if self.url_valid is False:
            QMessageBox.critical(
                self,
                "Cannot Download",
                f"This URL cannot be downloaded:\n{self.url_status_label.text()}\n\nPlease check the URL or try a different source."
            )
            return

        # If path is just a directory, append filename from URL
        if os.path.isdir(path):
            filename = extract_filename_from_url(url)
            if filename:
                path = os.path.join(path, filename)
            else:
                QMessageBox.warning(self, "Invalid URL", "Cannot determine filename from URL. Please specify a full path.")
                return

        self.url = url
        self.selected_path = path
        self.speed_limit = self.speed_limit_spin.value()
        super().accept()
