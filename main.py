#!/usr/bin/env python3
"""
Roxy Download Manager with PyQt6 + curl CLI
Dark theme, custom title bar, multiple downloads, pause/resume, speed limit.
+ Per‑item action buttons, persistent completed downloads.
"""

import sys
import os
import subprocess
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon, QPalette, QColor
from PyQt6.QtCore import QDir

from utils.constants import DARK_QSS, APP_NAME, APP_ORG_NAME, APP_ID, SINGLE_INSTANCE_PORT
from utils.helpers import get_resource_path, set_taskbar_icon
from ui import MainWindow
from server import SingleInstanceManager


def main():
    # Check for single instance
    single_instance = SingleInstanceManager(port=SINGLE_INSTANCE_PORT)
    
    # Check if we're the first instance
    if not single_instance.acquire_lock():
        # Another instance is running
        # Check if we have URL arguments to send to the running instance
        if len(sys.argv) > 1:
            # Handle roxy:// protocol and direct URLs
            url = sys.argv[1]
            filename_from_args = None
            
            if url.startswith('roxy://'):
                # Extract URL from protocol
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(url)
                    if parsed.query:
                        params = parse_qs(parsed.query)
                        if 'url' in params:
                            url = params['url'][0]
                except Exception:
                    pass
            elif url.startswith('http://') or url.startswith('https://'):
                pass  # URL is already in correct format
            elif url.startswith('--filename='):
                # Handle filename argument (should come after URL)
                filename_from_args = url.split('=', 1)[1]
                if len(sys.argv) > 2:
                    next_arg = sys.argv[2]
                    if next_arg.startswith('http://') or next_arg.startswith('https://'):
                        url = next_arg
            
            # Check for --filename in any argument
            for arg in sys.argv:
                if arg.startswith('--filename='):
                    filename_from_args = arg.split('=', 1)[1]
            
            if url.startswith('http://') or url.startswith('https://'):
                single_instance.send_to_running_instance(url, filename_from_args)
                print(f"Sent URL to running instance: {url}")
                sys.exit(0)
        else:
            print("Roxy is already running")
            sys.exit(0)
    
    try:
        subprocess.run(["curl", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        QMessageBox.critical(None, "curl not found", "curl is required but was not found in PATH.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(QPalette(QColor("#1e1e1e")))
    
    # Set application name and organization for better taskbar integration
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG_NAME)
    
    # Set application icon for taskbar using Windows API
    icon_path = get_resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        try:
            set_taskbar_icon(icon_path, APP_ID)
        except Exception as e:
            print(f"Could not set taskbar icon: {e}")
    
    window = MainWindow()
    
    # Set window icon for titlebar (even though we have custom title bar)
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    
    # Store single instance manager in window for cleanup
    window.single_instance = single_instance
    
    # Start listening for connections from other instances
    single_instance.listen_for_connections(window.add_download_from_api)
    
    window.show()
    
    # Check for roxy:// protocol or URL argument
    url_to_download = None
    filename_from_args = None
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        if url.startswith('roxy://'):
            # Extract URL from protocol
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    if 'url' in params:
                        url_to_download = params['url'][0]
            except Exception:
                pass
        elif url.startswith('http://') or url.startswith('https://'):
            url_to_download = url
        elif url.startswith('--filename='):
            # Handle filename argument (should come after URL)
            filename_from_args = url.split('=', 1)[1]
            if len(sys.argv) > 2:
                next_arg = sys.argv[2]
                if next_arg.startswith('http://') or next_arg.startswith('https://'):
                    url_to_download = next_arg
    
    # Check for --filename in any argument
    for arg in sys.argv:
        if arg.startswith('--filename='):
            filename_from_args = arg.split('=', 1)[1]
    
    if url_to_download:
        window.add_download_from_api(url_to_download, filename_from_args)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
