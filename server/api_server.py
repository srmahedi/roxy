"""
HTTP API Server for Chrome Extension Integration
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from utils.constants import MAIN_API_PORT


class RoxyAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Chrome extension integration."""
    
    def __init__(self, *args, main_window=None, **kwargs):
        self.main_window = main_window
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests for status check and settings."""
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response = {'status': 'running', 'message': 'Roxy is running'}
            self.wfile.write(json.dumps(response).encode('utf-8'))
        elif self.path == '/api/settings':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            # Return default settings (in a real implementation, this would load from config)
            response = {
                'browser': {
                    'menu': {
                        'dllink': '1',
                        'dlall': '1',
                        'dlselected': '1',
                        'dlpage': '1',
                        'dlvideo': '1',
                        'dlYtChannel': '0',
                        'dlYtPlaylist': '0'
                    },
                    'monitor': {
                        'enable': '1',
                        'allowDownload': '1',
                        'skipSmallerThan': '1024',
                        'skipExtensions': '',
                        'skipServers': '',
                        'skipServersEnabled': '0',
                        'catchExtensions': '',
                        'skipIfKeyPressed': '0'
                    }
                }
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404, "Not found")
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests with download URLs and settings."""
        if self.path == '/api/download':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                url = data.get('url', '').strip()
                filename = data.get('filename', '').strip()
                referrer = data.get('referrer', '').strip()
                cookies = data.get('cookies', '').strip()
                userAgent = data.get('userAgent', '').strip()
                postData = data.get('postData', '').strip()
                documentUrl = data.get('documentUrl', '').strip()
                
                print(f"🔍 DEBUG: Received URL in HTTP API: {url}")
                print(f"🔍 DEBUG: Received filename in HTTP API: {filename}")
                print(f"🔍 DEBUG: Additional data - referrer: {referrer}, cookies: {cookies[:50] if cookies else 'none'}...")
                print(f"🔍 DEBUG: Main window available: {self.main_window is not None}")
                
                if not url:
                    self.send_error(400, "URL is required")
                    return
                
                # Send success response with CORS headers
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {'status': 'success', 'message': 'Download added', 'result': '1'}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                print(f"🔍 DEBUG: Sent success response for URL: {url}")
                
                # Add download to main window using a signal for thread safety
                if self.main_window:
                    print(f"🔍 DEBUG: Scheduling download add for URL: {url}")
                    # Use a signal for thread-safe communication
                    try:
                        # Enhanced download info with additional parameters
                        download_info = {
                            'url': url,
                            'filename': filename,
                            'referrer': referrer,
                            'cookies': cookies,
                            'userAgent': userAgent,
                            'postData': postData,
                            'documentUrl': documentUrl
                        }
                        # Store the additional info temporarily and emit basic signal
                        self.main_window._pending_download_info = download_info
                        self.main_window.download_requested.emit(url, filename)
                        print(f"🔍 DEBUG: Emitted download_requested signal for URL: {url}")
                    except Exception as e:
                        print(f"🔍 DEBUG: Failed to emit signal: {e}")
                        # Fallback to direct call
                        self.main_window.add_download_from_api(url, filename)
                else:
                    print(f"🔍 DEBUG: ERROR - No main window available to add download")
                    
            except Exception as e:
                print(f"🔍 DEBUG: ERROR in HTTP API handler: {e}")
                self.send_error(500, f"Internal server error: {str(e)}")
        elif self.path == '/api/settings':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                print(f"🔍 DEBUG: Received settings update: {data}")
                
                # Store settings (in a real implementation, this would save to config)
                if self.main_window and hasattr(self.main_window, 'update_settings'):
                    self.main_window.update_settings(data)
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {'status': 'success', 'message': 'Settings updated'}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            except Exception as e:
                print(f"🔍 DEBUG: ERROR in settings handler: {e}")
                self.send_error(500, f"Internal server error: {str(e)}")
        else:
            self.send_error(404, "Not found")
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class RoxyAPIServer:
    """HTTP server for Chrome extension communication."""
    
    def __init__(self, port=MAIN_API_PORT, main_window=None):
        self.port = port
        self.main_window = main_window
        self.server = None
        self.server_thread = None
        
    def start(self):
        """Start the HTTP server in a separate thread."""
        def handler(*args, **kwargs):
            return RoxyAPIHandler(*args, main_window=self.main_window, **kwargs)
        
        self.server = HTTPServer(('localhost', self.port), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        print(f"Roxy API server started on http://localhost:{self.port}")
        
    def stop(self):
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            if self.server_thread:
                self.server_thread.join()
            print("Roxy API server stopped")
