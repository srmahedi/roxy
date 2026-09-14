"""
Duplicate Download Dialog for Roxy Download Manager
Prompts user when adding a file/URL that already exists.
"""
import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QStyle
)
from utils.constants import DARK_QSS


class DuplicateDownloadDialog(QDialog):
    ACTION_OVERWRITE = "overwrite"
    ACTION_RENAME = "rename"
    ACTION_CANCEL = "cancel"

    def __init__(self, parent=None, filename="", url="", save_path="", is_file_duplicate=True, is_url_duplicate=False):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Download Detected")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(DARK_QSS)

        self.action = self.ACTION_CANCEL

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header section with Warning icon
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        warning_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        icon_label.setPixmap(warning_icon.pixmap(36, 36))
        header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        title_label = QLabel("<b>Duplicate Download Detected</b>")
        title_label.setStyleSheet("font-size: 15px; color: #FFFFFF;")
        title_layout.addWidget(title_label)

        reason_text = []
        if is_file_duplicate:
            reason_text.append("A file with this name already exists in the save location.")
        if is_url_duplicate:
            reason_text.append("This URL is already present in your download list.")
        
        reason_label = QLabel(" ".join(reason_text))
        reason_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        reason_label.setWordWrap(True)
        title_layout.addWidget(reason_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Info Box
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #252526; border: 1px solid #3E3E42; border-radius: 6px; padding: 10px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(6)

        file_info = QLabel(f"<b>File:</b> {filename}")
        file_info.setStyleSheet("color: #E0E0E0;")
        file_info.setWordWrap(True)
        info_layout.addWidget(file_info)

        path_info = QLabel(f"<b>Location:</b> {save_path}")
        path_info.setStyleSheet("color: #888888; font-size: 11px;")
        path_info.setWordWrap(True)
        info_layout.addWidget(path_info)

        if url:
            url_info = QLabel(f"<b>URL:</b> {url}")
            url_info.setStyleSheet("color: #888888; font-size: 11px;")
            url_info.setWordWrap(True)
            info_layout.addWidget(url_info)

        layout.addWidget(info_frame)

        # Description / Question
        prompt_label = QLabel("What would you like to do?")
        prompt_label.setStyleSheet("color: #CCCCCC; font-size: 13px; font-weight: bold;")
        layout.addWidget(prompt_label)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Rename / Download Again Button (Recommended Default)
        self.rename_btn = QPushButton("🔢 Download Again")
        self.rename_btn.setToolTip("Saves as a new file with sequence number (e.g. file (1).ext)")
        self.rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0098FF;
            }
        """)
        self.rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(self.rename_btn)

        # Overwrite Button
        self.overwrite_btn = QPushButton("🔄 Overwrite")
        self.overwrite_btn.setToolTip("Replaces existing file on disk and overwrites existing entry")
        self.overwrite_btn.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #555555;
            }
            QPushButton:hover {
                background-color: #D32F2F;
                border-color: #F44336;
            }
        """)
        self.overwrite_btn.clicked.connect(self._on_overwrite)
        btn_layout.addWidget(self.overwrite_btn)

        # Cancel / Skip Button
        self.cancel_btn = QPushButton("❌ Skip / Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D30;
                color: #CCCCCC;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #444444;
            }
            QPushButton:hover {
                background-color: #3E3E42;
                color: white;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _on_rename(self):
        self.action = self.ACTION_RENAME
        self.accept()

    def _on_overwrite(self):
        self.action = self.ACTION_OVERWRITE
        self.accept()

    def _on_cancel(self):
        self.action = self.ACTION_CANCEL
        self.reject()
