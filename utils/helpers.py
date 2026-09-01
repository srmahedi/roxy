"""
Helper functions for Roxy Download Manager
"""
import sys
import os
import ctypes


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
