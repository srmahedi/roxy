"""
Add URL Dialog for adding new downloads
"""
import os
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QDialogButtonBox, QMessageBox, QFileDialog
)
from utils.constants import DARK_QSS
from utils.helpers import extract_filename_from_url


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

    def accept(self):
        url = self.url_edit.text().strip()
        path = self.save_path_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a URL.")
            return
        if not path:
            QMessageBox.warning(self, "Missing Save Path", "Please choose a save location.")
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
