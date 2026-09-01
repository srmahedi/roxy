"""
Constants for Roxy Download Manager
"""

# Dark Theme Stylesheet (global)
DARK_QSS = """
* {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 12px;
}
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QWidget {
    background-color: #1e1e1e;
}
QTableView {
    background-color: #252526;
    alternate-background-color: #2d2d30;
    gridline-color: #3f3f46;
    selection-background-color: #094771;
    border: 1px solid #3f3f46;
}
QHeaderView::section {
    background-color: #2d2d30;
    color: #cccccc;
    padding: 4px;
    border: 1px solid #3f3f46;
}
QToolBar {
    background-color: #2d2d30;
    border: none;
    spacing: 3px;
    padding: 2px;
}
QStatusBar {
    background-color: #2d2d30;
    color: #cccccc;
    border-top: 1px solid #3f3f46;
}
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    padding: 5px 10px;
    border-radius: 3px;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:pressed {
    background-color: #2a2a2a;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #888888;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    padding: 4px;
    border-radius: 3px;
}
QProgressBar {
    background-color: #2d2d30;
    border: 1px solid #3f3f46;
    border-radius: 3px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background-color: #007acc;
    border-radius: 3px;
}
QMenuBar {
    background-color: #2d2d30;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected {
    background: #3c3c3c;
}
QMenu {
    background-color: #2d2d30;
    border: 1px solid #555555;
}
QMenu::item:selected {
    background-color: #094771;
}
QScrollBar:vertical {
    background: #2d2d30;
    width: 12px;
    border-radius: 6px;
}
QScrollBar:handle:vertical {
    background: #555555;
    border-radius: 6px;
    min-height: 20px;
}
QScrollBar:add-line:vertical, QScrollBar:sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #2d2d30;
    height: 12px;
    border-radius: 6px;
}
QScrollBar:handle:horizontal {
    background: #555555;
    border-radius: 6px;
    min-width: 20px;
}
QScrollBar:add-line:horizontal, QScrollBar:sub-line:horizontal {
    width: 0px;
}
"""

# API Ports
LAUNCHER_PORT = 12579
MAIN_API_PORT = 12580
SINGLE_INSTANCE_PORT = 12581

# App info
APP_NAME = "Roxy Download Manager"
APP_ORG_NAME = "Roxy"
APP_ID = "Roxy.DownloadManager"
