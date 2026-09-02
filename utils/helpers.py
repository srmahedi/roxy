"""
Helper functions for Roxy Download Manager
"""
import sys
import os
import ctypes
import re
import subprocess
from urllib.parse import unquote


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if getattr(sys, 'frozen', False):
        # If we're running as a PyInstaller bundle
        base_dir = os.path.dirname(sys.executable)
    else:
        # If we're running as a normal Python script
        # Get the project root directory (where main.py is located)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_dir, relative_path)


def force_window_to_foreground(window_handle=None):
    """Force window to foreground using Windows API."""
    if sys.platform != "win32":
        return
    
    try:
        # Use provided window handle or find by title
        if window_handle:
            hwnd = int(window_handle)
        else:
            # Find the Roxy window by title
            from utils.constants import APP_NAME
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
        
        if hwnd == 0:
            print("Could not find Roxy window handle")
            return
        
        # Get the thread ID of the foreground window
        foreground_thread = ctypes.windll.user32.GetWindowThreadProcessId(
            ctypes.windll.user32.GetForegroundWindow(), None
        )
        
        # Get the thread ID of the current process
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        
        # Attach to the foreground thread
        ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True)
        
        # Restore the window if minimized
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        
        # Set the window to foreground
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        
        # Detach from the thread
        ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)
        
    except Exception as e:
        print(f"Error forcing window to foreground: {e}")


def set_taskbar_icon(icon_path: str, app_id: str = "Roxy.DownloadManager", force_window: bool = False):
    """
    Sets the taskbar icon for Windows apps using the provided .ico file.
    Works with GUI frameworks and CLI apps (with optional hidden window).

    Args:
        icon_path (str): Path to the .ico file
        app_id (str): Custom AppUserModelID for taskbar grouping
        force_window (bool): If True, creates a hidden window for CLI apps
    """
    if not os.path.exists(icon_path):
        raise FileNotFoundError(f"Icon file not found: {icon_path}")

    if sys.platform != "win32":
        return  # Only relevant on Windows

    try:
        # Set the AppUserModelID for proper taskbar grouping
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        
    except Exception as e:
        print(f"Could not set AppUserModelID: {e}")


def extract_filename_from_url(url: str, provided_filename: str = None) -> str:
    """
    Extract the real filename from a URL using HTTP headers.
    Falls back to URL parsing if headers don't provide a filename.
    
    Args:
        url: The URL to extract filename from
        provided_filename: Optional filename provided by Chrome extension or other source
        
    Returns:
        The extracted filename with proper extension
    """
    # If a filename is provided and it's not a UUID, use it
    if provided_filename and provided_filename.strip():
        decoded_filename = unquote(provided_filename.strip())
        # Check if it's a UUID (common when extension can't extract filename)
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, decoded_filename.lower()):
            return decoded_filename
    
    # Try to get filename from HTTP headers using curl
    try:
        cmd = ["curl", "-sIL", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        headers = result.stdout
        
        # Check Content-Disposition header for filename
        content_disposition_matches = re.findall(r'[Cc]ontent-[Dd]isposition:\s*(.+)', headers)
        for match in content_disposition_matches:
            # Try to extract filename from Content-Disposition
            filename_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\s]+)["\']?', match, re.IGNORECASE)
            if filename_match:
                filename = filename_match.group(1)
                # URL decode the filename
                filename = unquote(filename)
                if filename and len(filename) > 3:
                    print(f"DEBUG: Extracted filename from Content-Disposition: {filename}")
                    return filename
        
        # Check for filename in regular Content-Disposition without encoding
        for match in content_disposition_matches:
            filename_match = re.search(r'filename="?([^"\';]+)"?', match, re.IGNORECASE)
            if filename_match:
                filename = filename_match.group(1)
                filename = unquote(filename)
                if filename and len(filename) > 3:
                    print(f"DEBUG: Extracted filename from Content-Disposition (simple): {filename}")
                    return filename
    except Exception as e:
        print(f"DEBUG: Error getting filename from headers: {e}")
    
    # Fallback to URL-based extraction
    url_path = url.split('?')[0]  # Remove query parameters
    filename = os.path.basename(url_path)
    
    # Handle common URL patterns that don't end with filename
    if not filename or len(filename) < 3 or '.' not in filename or filename == 'example.com' or filename == 'www.example.com' or filename == 'download':
        # Try to extract from the last path segment that looks like a file
        path_segments = url_path.split('/')
        for segment in reversed(path_segments):
            if segment and '.' in segment and len(segment) > 3 and not segment.startswith('www.') and not segment.endswith('.com'):
                filename = segment
                break
        
        # If still no good filename, try to get from URL parameters
        if not filename or len(filename) < 3 or filename == 'example.com' or filename == 'www.example.com' or filename == 'download':
            # Look for common filename parameters in the full URL
            param_patterns = [r'[?&]filename=([^&]+)', r'[?&]file=([^&]+)', r'[?&]name=([^&]+)']
            for pattern in param_patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    filename = unquote(match.group(1))
                    if filename and len(filename) > 3:
                        print(f"DEBUG: Extracted filename from URL parameter: {filename}")
                        return filename
    
    # Decode URL-encoded filename
    filename = unquote(filename)
    
    # Final fallback
    if not filename or len(filename) < 3 or filename == 'example.com' or filename == 'www.example.com' or filename == 'download':
        filename = "download"
    
    print(f"DEBUG: Using fallback filename from URL: {filename}")
    return filename
