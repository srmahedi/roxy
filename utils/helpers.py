"""
Helper functions for Roxy Download Manager
"""
import sys
import os
import ctypes
import re
from urllib.parse import unquote
import mimetypes
import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"



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


def sanitize_filename(filename: str, default_name: str = "download") -> str:
    """
    Sanitize a filename by removing query strings and illegal OS characters.
    """
    if not filename:
        return default_name

    # Unquote URL-encoded characters
    filename = unquote(filename.strip())

    # Remove query string parameters and fragment identifiers
    filename = filename.split('?')[0].split('#')[0].strip()

    # Remove invalid Windows/Linux filename characters: < > : " / \ | ? *
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

    # Strip trailing periods and spaces (invalid on Windows)
    filename = filename.rstrip('. ')

    # Limit filename length to 200 characters
    if len(filename) > 200:
        base, ext = os.path.splitext(filename)
        filename = base[:190] + ext

    return filename or default_name


def extract_filename_from_url(url: str, provided_filename: str = None,
                              cookies: str = None, referrer: str = None) -> str:
    """
    Extract the real filename from a URL using HTTP headers.
    Falls back to URL parsing if headers don't provide a filename.
    
    Args:
        url: The URL to extract filename from
        provided_filename: Optional filename provided by Chrome extension or other source
        cookies: Optional Cookie header string (e.g. from the browser extension) used
                 when probing authenticated URLs such as Google Drive.
        referrer: Optional Referer header string.
        
    Returns:
        The extracted filename with proper extension
    """
    # If a valid filename is provided with extension and is not generic or a UUID, use it
    if provided_filename and provided_filename.strip():
        # Discard if provided_filename looks like a raw URL or URL path segment
        # (e.g. extension bug: "download?id=abc&export=..." sent as filename)
        _pf = provided_filename.strip()
        if _pf.startswith(('http://', 'https://', 'ftp://')) or '/' in _pf or '?' in _pf:
            provided_filename = None

    if provided_filename and provided_filename.strip():
        clean_provided = sanitize_filename(provided_filename)
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        name_without_ext, ext = os.path.splitext(clean_provided)
        is_uuid = bool(re.match(uuid_pattern, name_without_ext.lower()))
        is_generic = name_without_ext.lower() in ('download', 'file', 'index', 'view', 'stream', 'attachment')
        
        if not is_uuid and not is_generic and ext:
            return clean_provided

    # Check if this is a Google Drive URL and resolve filename via gdrive_resolver
    try:
        from utils.gdrive_resolver import is_google_drive_url, resolve_gdrive_download
        if is_google_drive_url(url):
            _, g_name, _, _ = resolve_gdrive_download(url, cookies=cookies, referrer=referrer, timeout=10)
            if g_name and len(g_name) > 3:
                return sanitize_filename(g_name)
    except Exception as e:
        print(f"DEBUG: Error resolving Google Drive filename: {e}")
    
    # Build request headers, including optional auth cookies / referrer
    probe_headers = {'User-Agent': USER_AGENT}
    if cookies:
        probe_headers['Cookie'] = cookies
    if referrer:
        probe_headers['Referer'] = referrer

    # Try to get filename from HTTP headers using HTTP HEAD/GET request
    _resp_for_content_type = None
    try:
        resp = None
        try:
            resp = requests.head(url, headers=probe_headers, allow_redirects=True, timeout=5)
            if resp.status_code not in (200, 206):
                resp = None
        except Exception:
            resp = None

        if resp is None:
            try:
                resp = requests.get(url, headers=probe_headers, stream=True, allow_redirects=True, timeout=5)
            except Exception:
                resp = None

        if resp is not None:
            # Keep a reference to use Content-Type later as a fallback
            _resp_for_content_type = resp

            if 'content-disposition' in resp.headers:
                content_disposition = resp.headers['content-disposition']
                filename_match = re.search(r'filename\*=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)["\']?', content_disposition, re.IGNORECASE)
                if not filename_match:
                    filename_match = re.search(r'filename=["\']?([^"\';\r\n]+)["\']?', content_disposition, re.IGNORECASE)
                
                if filename_match:
                    filename = filename_match.group(1).strip('"\'')
                    if filename and len(filename) > 3:
                        resp.close()
                        return sanitize_filename(filename)
    except Exception as e:
        print(f"DEBUG: Error getting filename from headers: {e}")
    
    # Fallback to URL-based extraction
    url_path = url.split('?')[0].split('#')[0]  # Remove query parameters
    filename = os.path.basename(url_path)
    
    # Handle common URL patterns that don't end with filename
    generic_names = ('example.com', 'www.example.com', 'download', 'view', 'preview', 'edit')
    if not filename or len(filename) < 3 or '.' not in filename or filename.lower() in generic_names:
        path_segments = url_path.split('/')
        for segment in reversed(path_segments):
            if segment and '.' in segment and len(segment) > 3 and not segment.startswith('www.') and not segment.endswith('.com'):
                filename = segment
                break
        
        if not filename or len(filename) < 3 or filename.lower() in generic_names:
            param_patterns = [r'[?&]filename=([^&]+)', r'[?&]file=([^&]+)', r'[?&]name=([^&]+)']
            for pattern in param_patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    filename = match.group(1)
                    if filename and len(filename) > 3:
                        return sanitize_filename(filename)
    
    # If provided_filename was given earlier (e.g. "download"), fallback to clean_provided if no header filename
    if provided_filename and provided_filename.strip():
        clean_provided = sanitize_filename(provided_filename)
        name_part, ext_part = os.path.splitext(clean_provided)
        if clean_provided and name_part.lower() not in ('download', 'file', 'index', 'view', 'stream', 'attachment'):
            if _resp_for_content_type is not None:
                _resp_for_content_type.close()
            return clean_provided

    final_name = sanitize_filename(filename)
    if not final_name or len(final_name) < 3 or final_name.lower() in generic_names:
        # Last resort: use Content-Type header to determine the file extension
        ext = _guess_extension_from_response(_resp_for_content_type)
        final_name = f"download{ext}" if ext else "download"

    if _resp_for_content_type is not None:
        try:
            _resp_for_content_type.close()
        except Exception:
            pass

    return final_name


def _guess_extension_from_response(resp) -> str:
    """
    Guess a file extension from an HTTP response's Content-Type header.
    Returns a string like '.mp4' or '' if unknown.
    """
    if resp is None:
        return ''
    content_type = resp.headers.get('content-type', '')
    # Strip parameters like '; charset=utf-8'
    mime_type = content_type.split(';')[0].strip().lower()
    if not mime_type or mime_type in ('application/octet-stream', 'text/html', 'text/plain'):
        return ''
    ext = mimetypes.guess_extension(mime_type)
    if ext:
        # mimetypes can return unusual aliases; normalize some common ones
        _aliases = {
            '.jpe': '.jpg',
            '.jpeg': '.jpg',
            '.htm': '.html',
            '.mpga': '.mp3',
            '.m1v': '.mpeg',
        }
        ext = _aliases.get(ext, ext)
    return ext or ''


def get_unique_filepath(save_path: str, existing_paths=None) -> str:
    """
    Generate a unique filepath by appending (1), (2), etc. if the file exists on disk
    or in the list of existing active download paths.
    
    Example:
        C:/Downloads/video.mp4 -> C:/Downloads/video (1).mp4
    """
    if existing_paths is None:
        existing_paths = []
    
    # Normalize paths for accurate comparison
    norm_existing = {os.path.normpath(p).lower() for p in existing_paths if p}

    def _exists(path):
        norm = os.path.normpath(path).lower()
        return os.path.exists(path) or norm in norm_existing

    if not _exists(save_path):
        return save_path

    directory, filename = os.path.split(save_path)
    base_name, ext = os.path.splitext(filename)

    counter = 1
    while True:
        new_filename = f"{base_name} ({counter}){ext}"
        candidate_path = os.path.join(directory, new_filename)
        if not _exists(candidate_path):
            return candidate_path
        counter += 1

