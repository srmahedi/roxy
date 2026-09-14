"""
Custom Title Bar widget
"""
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from utils.helpers import get_resource_path
from utils.constants import APP_NAME


class TitleBar(QWidget):
    """Dark custom title bar with window controls."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(32)
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Window)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(4)

        # Add application icon to title bar
        icon_path = get_resource_path("icon.ico")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon = QIcon(icon_path)
            if not icon.isNull():
                icon_label.setPixmap(icon.pixmap(20, 20))
                icon_label.setStyleSheet("background: transparent;")
                layout.addWidget(icon_label)

        self.title_label = QLabel(APP_NAME)
        self.title_label.setStyleSheet("font-weight: bold; color: #cccccc; background: transparent;")
        layout.addWidget(self.title_label)

        layout.addStretch()

        self.min_btn = QPushButton("─")
        self.min_btn.setFixedSize(30, 24)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.parent.showMinimized)
        self.min_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #cccccc;
                font-size: 14px;
            }
            QPushButton:hover { background: #3c3c3c; }
        """)
        layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setFixedSize(30, 24)
        self.max_btn.setToolTip("Maximize/Restore")
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.max_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #cccccc;
                font-size: 14px;
            }
            QPushButton:hover { background: #3c3c3c; }
        """)
        layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 24)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.parent.close)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #cccccc;
                font-size: 14px;
            }
            QPushButton:hover { background: #e81123; color: white; }
        """)
        layout.addWidget(self.close_btn)

        self.normal_geometry = None

    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("□")
        else:
            self.normal_geometry = self.parent.geometry()
            self.parent.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent.moving = True
            self.parent.offset = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self.parent, 'moving') and self.parent.moving:
            self.parent.move(event.globalPosition().toPoint() - self.parent.offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self.parent, 'moving'):
            self.parent.moving = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.toggle_maximize()
        super().mouseDoubleClickEvent(event)
