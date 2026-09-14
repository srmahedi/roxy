"""
Google Drive URL Resolver for Roxy Download Manager
Handles resolving Google Drive viewer URLs, export URLs, virus scan warnings,
confirmation forms, dynamic tokens (uuid/confirm), and extracting real filenames.
"""

import re
import urllib.parse
from typing import Optional, Tuple
import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def is_google_drive_url(url: str) -> bool:
    """Check if the given URL is a Google Drive URL."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        hostname = (parsed.hostname or '').lower()
        return (
            hostname in ('drive.google.com', 'docs.google.com', 'drive.usercontent.google.com')
            or (hostname.endswith('.google.com') and 'drive' in hostname)
        )
    except Exception:
        return False


def extract_gdrive_file_id(url: str) -> Optional[str]:
    """Extract Google Drive File ID from various URL formats."""
    if not url:
        return None

    # Format 1: /file/d/<file_id>/view or /file/d/<file_id>
    m = re.search(r'/file/d/([a-zA-Z0-9_-]{20,})', url)
    if m:
        return m.group(1)

    # Format 2: ?id=<file_id> or &id=<file_id>
    m = re.search(r'[?&]id=([a-zA-Z0-9_-]{20,})', url)
    if m:
        return m.group(1)

    # Format 3: /open?id=<file_id>
    m = re.search(r'/open\?[^#]*id=([a-zA-Z0-9_-]{20,})', url)
    if m:
        return m.group(1)

    # Format 4: /folders/<folder_id>
    m = re.search(r'/folders/([a-zA-Z0-9_-]{20,})', url)
    if m:
        return m.group(1)

    return None


def extract_filename_from_content_disposition(content_disp: str) -> Optional[str]:
    """Extract filename from Content-Disposition header."""
    if not content_disp:
        return None

    # filename*=UTF-8''filename.ext
    m = re.search(r"filename\*=(?:UTF-8'')?['\"]?([^;'\"]+)['\"]?", content_disp, re.IGNORECASE)
    if m:
        return urllib.parse.unquote(m.group(1).strip())

    # filename="filename.ext" or filename=filename.ext
    m = re.search(r'filename=["\']?([^";\r\n]+)["\']?', content_disp, re.IGNORECASE)
    if m:
        return urllib.parse.unquote(m.group(1).strip())

    return None


def resolve_gdrive_download(
    url: str,
    session: Optional[requests.Session] = None,
    cookies: Optional[str] = None,
    referrer: Optional[str] = None,
    timeout: int = 15
) -> Tuple[str, Optional[str], Optional[int], Optional[str]]:
    """
    Resolves a Google Drive URL to a direct downloadable URL.
    Handles:
      - /file/d/<id>/view -> direct download link
      - Virus scan warning confirmation page (with form tokens or downloadUrl)
      - Filename extraction from Content-Disposition or HTML
      - Error detection (quota exceeded, access denied, not found)

    Returns:
        (resolved_url, suggested_filename, file_size, error_message)
    """
    if not is_google_drive_url(url):
        return url, None, None, None

    s = session or requests.Session()
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    if cookies:
        headers['Cookie'] = cookies
    if referrer:
        headers['Referer'] = referrer

    file_id = extract_gdrive_file_id(url)

    # If the URL is a viewer/preview URL, change it to direct download URL
    target_url = url
    if file_id and ('/view' in url or '/edit' in url or '/open' in url or 'export=download' not in url):
        target_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"

    try:
        resp = s.get(target_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout)
    except Exception as e:
        return target_url, None, None, f"Network error connecting to Google Drive: {str(e)}"

    content_type = resp.headers.get('Content-Type', '').lower()
    content_disp = resp.headers.get('Content-Disposition', '')

    # Case A: Direct file stream returned
    if resp.status_code in (200, 206) and ('attachment' in content_disp or 'text/html' not in content_type):
        filename = extract_filename_from_content_disposition(content_disp)
        size = None
        cl = resp.headers.get('Content-Length')
        if cl and cl.isdigit():
            size = int(cl)
        final_url = resp.url
        resp.close()
        return final_url, filename, size, None

    # Case B: Server returned HTML page (could be confirmation page or error page)
    if 'text/html' in content_type or resp.status_code != 200:
        html_chunks = []
        try:
            for chunk in resp.iter_content(chunk_size=32768, decode_unicode=True):
                if isinstance(chunk, bytes):
                    chunk = chunk.decode('utf-8', errors='ignore')
                html_chunks.append(chunk)
                if sum(len(c) for c in html_chunks) > 2 * 1024 * 1024:  # read at most 2MB of HTML
                    break
        except Exception:
            pass
        finally:
            resp.close()

        html_text = "".join(html_chunks)

        # 1. Check for specific Google Drive error conditions
        if "Download quota exceeded" in html_text or ("quota" in html_text.lower() and "exceeded" in html_text.lower()):
            return target_url, None, None, "Google Drive error: Download quota exceeded for this file. Try again later."

        if "You need access" in html_text or "Sign in to continue" in html_text or "accounts.google.com" in resp.url:
            return target_url, None, None, "Google Drive error: This file is private or requires sign-in permission."

        if resp.status_code == 404 or "The requested URL was not found on this server" in html_text:
            return target_url, None, None, "Google Drive error: File not found (404). Check the link."

        # 2. Extract potential filename from the HTML warning page
        suggested_name = None
        fn_match = re.search(r'<span class="uc-name-size"[^>]*>.*?<a[^>]*>([^<]+)</a>', html_text, re.DOTALL)
        if fn_match:
            suggested_name = fn_match.group(1).strip()
        if not suggested_name:
            title_match = re.search(r'<title>([^\n<]+?)(?: - Google Drive)?</title>', html_text, re.IGNORECASE)
            if title_match:
                t = title_match.group(1).strip()
                if t and "virus scan warning" not in t.lower() and "error" not in t.lower():
                    suggested_name = t

        # 3. Check for virus scan confirmation form:
        # <form id="download-form" action="https://drive.usercontent.google.com/download" method="get">
        form_match = re.search(r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>', html_text, re.DOTALL | re.IGNORECASE)
        if form_match:
            action_url = form_match.group(1).replace('&amp;', '&')
            if not action_url.startswith(('http://', 'https://')):
                action_url = urllib.parse.urljoin("https://drive.usercontent.google.com", action_url)

            form_content = form_match.group(2)
            inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', form_content, re.IGNORECASE)

            parsed_action = urllib.parse.urlsplit(action_url)
            query_params = urllib.parse.parse_qs(parsed_action.query)
            for k, v in inputs:
                query_params[k] = [v]

            new_query = urllib.parse.urlencode(query_params, doseq=True)
            confirmed_url = urllib.parse.urlunsplit(parsed_action._replace(query=new_query))

            try:
                conf_resp = s.get(confirmed_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout)
                if conf_resp.status_code in (200, 206):
                    cd = conf_resp.headers.get('Content-Disposition', '')
                    actual_name = extract_filename_from_content_disposition(cd) or suggested_name
                    size = None
                    cl = conf_resp.headers.get('Content-Length')
                    if cl and cl.isdigit():
                        size = int(cl)
                    final_url = conf_resp.url
                    conf_resp.close()
                    return final_url, actual_name, size, None
                conf_resp.close()
            except Exception as e:
                return confirmed_url, suggested_name, None, f"Error confirming Google Drive download: {str(e)}"

        # 4. Check for JSON "downloadUrl":"..."
        url_match = re.search(r'"downloadUrl":"([^"]+)"', html_text)
        if url_match:
            confirmed_url = url_match.group(1).replace('\\u003d', '=').replace('\\u0026', '&')
            try:
                conf_resp = s.get(confirmed_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout)
                if conf_resp.status_code in (200, 206):
                    cd = conf_resp.headers.get('Content-Disposition', '')
                    actual_name = extract_filename_from_content_disposition(cd) or suggested_name
                    size = None
                    cl = conf_resp.headers.get('Content-Length')
                    if cl and cl.isdigit():
                        size = int(cl)
                    final_url = conf_resp.url
                    conf_resp.close()
                    return final_url, actual_name, size, None
                conf_resp.close()
            except Exception:
                pass

        # 5. Check for legacy uc-download-link: <a id="uc-download-link" href="...">
        link_match = re.search(r'id="uc-download-link"[^>]*href="([^"]+)"', html_text)
        if link_match:
            rel_link = link_match.group(1).replace('&amp;', '&')
            confirmed_url = urllib.parse.urljoin("https://drive.google.com", rel_link)
            try:
                conf_resp = s.get(confirmed_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout)
                if conf_resp.status_code in (200, 206):
                    cd = conf_resp.headers.get('Content-Disposition', '')
                    actual_name = extract_filename_from_content_disposition(cd) or suggested_name
                    size = None
                    cl = conf_resp.headers.get('Content-Length')
                    if cl and cl.isdigit():
                        size = int(cl)
                    final_url = conf_resp.url
                    conf_resp.close()
                    return final_url, actual_name, size, None
                conf_resp.close()
            except Exception:
                pass

    return target_url, None, None, None
