"""
Settings Dialog for Roxy Download Manager
"""
import os
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QDialogButtonBox, QFileDialog, QMessageBox
)
from utils.constants import DARK_QSS


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet(DARK_QSS)
        self.settings_manager = settings_manager

        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Default download path
        self.default_path_edit = QLineEdit()
        self.default_path_edit.setPlaceholderText("Default download folder...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_default_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.default_path_edit)
        path_layout.addWidget(browse_btn)
        form.addRow("Default Download Path:", path_layout)

        # Max concurrent downloads
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setSuffix(" concurrent downloads")
        form.addRow("Max Concurrent Downloads:", self.concurrent_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Load current settings
        self.load_settings()

    def load_settings(self):
        """Load current settings into the dialog."""
        if self.settings_manager:
            default_path = self.settings_manager.get_setting('default_download_path', '')
            if not default_path:
                # Use OS Downloads folder as default
                default_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
                if not default_path or not os.path.isdir(default_path):
                    default_path = os.path.expanduser("~")
            self.default_path_edit.setText(default_path)

            max_concurrent = self.settings_manager.get_setting('max_concurrent_downloads', 3)
            self.concurrent_spin.setValue(max_concurrent)

    def browse_default_path(self):
        """Browse for default download path."""
        current_path = self.default_path_edit.text()
        if not current_path or not os.path.isdir(current_path):
            current_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not current_path or not os.path.isdir(current_path):
                current_path = os.path.expanduser("~")

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Default Download Folder",
            current_path
        )
        if folder_path:
            self.default_path_edit.setText(folder_path)

    def accept(self):
        """Save settings and close dialog."""
        if self.settings_manager:
            default_path = self.default_path_edit.text().strip()
            if default_path and os.path.isdir(default_path):
                self.settings_manager.save_setting('default_download_path', default_path)
            else:
                QMessageBox.warning(self, "Invalid Path", "Please select a valid folder for the default download path.")
                return

            max_concurrent = self.concurrent_spin.value()
            self.settings_manager.save_setting('max_concurrent_downloads', max_concurrent)

            # Apply concurrent downloads limit to parent window
            if self.parent():
                parent = self.parent()
                if hasattr(parent, 'max_concurrent_downloads'):
                    parent.max_concurrent_downloads = max_concurrent

        super().accept()
