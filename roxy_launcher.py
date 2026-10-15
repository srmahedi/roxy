#!/usr/bin/env python3
"""
Roxy Launcher Server
Receives download URLs from Chrome extension and opens Roxy.exe
"""

import subprocess
import sys
import json
import time
import os
import tempfile
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Ready signal file path for faster detection
ROXY_READY_FILE = os.path.join(tempfile.gettempdir(), "roxy_api_ready.txt")

class RoxyLauncherHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Handle CORS preflight requests
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/download':
            # Get the content length
            content_length = int(self.headers['Content-Length'])
            
            # Read the POST data
            post_data = self.rfile.read(content_length)
            
            try:
                # Parse the JSON data
                data = json.loads(post_data.decode('utf-8'))
                url = data.get('url')
                filename = data.get('filename')
                referrer = data.get('referrer', '')
                cookies = data.get('cookies', '')
                userAgent = data.get('userAgent', '')
                postData = data.get('postData', '')
                documentUrl = data.get('documentUrl', '')
                
                if url:
                    print(f"Received download URL: {url}")
                    print(f"URL type: {type(url)}")
                    print(f"URL length: {len(url)}")
                    if filename:
                        print(f"Received filename: {filename}")
                    
                    # Open Roxy.exe with full download payload parameters
                    self.open_roxy_with_url(
                        url,
                        filename,
                        referrer,
                        cookies,
                        userAgent,
                        postData,
                        documentUrl
                    )
                    
                    # Send success response
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    response = {'status': 'success', 'message': 'URL received and processed'}
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                    print("Response sent to extension")
                else:
                    # Send error response - no URL provided
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    response = {'status': 'error', 'message': 'No URL provided'}
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                    print("Error: No URL provided")
                    
            except json.JSONDecodeError:
                # Send error response - invalid JSON
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {'status': 'error', 'message': 'Invalid JSON'}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                print("Error: Invalid JSON")
            except Exception as e:
                # Send error response - server error
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = {'status': 'error', 'message': str(e)}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                print(f"Error: {e}")
        else:
            # Send 404 for unknown paths
            self.send_response(404)
            self.end_headers()
    
    def is_roxy_instance_running(self):
        """Check if Roxy instance is running by checking its HTTP API"""
        try:
            req = urllib.request.Request('http://localhost:12580/api/status', method='GET')
            with urllib.request.urlopen(req, timeout=0.2) as response:
                is_running = (response.status == 200)
                if is_running:
                    print("✓ Roxy instance detected via HTTP API on port 12580")
                else:
                    print("✗ Roxy API responded but not ready")
                return is_running
        except Exception as e:
            print(f"✗ HTTP API check failed: {e}")
            return False
    
    def is_roxy_instance_running_with_retry(self, retries=1, delay=0.1):
        """Check if Roxy instance is running with retry logic"""
        for i in range(retries):
            if self.is_roxy_instance_running():
                return True
            if i < retries - 1:
                print(f"Retrying Roxy detection in {delay}s... (attempt {i+2}/{retries})")
                time.sleep(delay)
        return False

    def check_roxy_ready_file(self):
        """Check if Roxy ready signal file exists (faster than HTTP check)"""
        try:
            if os.path.exists(ROXY_READY_FILE):
                # Verify Roxy is actually running by doing a quick HTTP check
                if self.is_roxy_instance_running():
                    print("✓ Roxy ready file detected and API confirmed")
                    return True
                else:
                    # File exists but API not ready - might be stale
                    print("⚠ Roxy ready file exists but API not responding, ignoring")
                    return False
        except Exception as e:
            print(f"✗ Ready file check failed: {e}")
        return False
    
    def open_roxy_with_url(
        self,
        url,
        filename=None,
        referrer='',
        cookies='',
        userAgent='',
        postData='',
        documentUrl=''
    ):
        """Open Roxy.exe and send full download payload to HTTP API"""
        try:
            print("=" * 50)
            print(f"Processing download URL: {url}")
            print("=" * 50)

            payload = {
                'url': url,
                'filename': filename or '',
                'referrer': referrer,
                'cookies': cookies,
                'userAgent': userAgent,
                'postData': postData,
                'documentUrl': documentUrl
            }

            # Check ready file first (much faster than HTTP)
            if self.check_roxy_ready_file():
                print("Roxy is running - sending full download information")
                data = json.dumps(payload).encode('utf-8')

                req = urllib.request.Request(
                    'http://localhost:12580/api/download',
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )

                with urllib.request.urlopen(req, timeout=2) as response:
                    print(f"Roxy response: {response.status}")
                return

            # Fallback to HTTP check if ready file not found
            if self.is_roxy_instance_running_with_retry(retries=1, delay=0.1):
                print("Roxy is running - sending full download information")
                data = json.dumps(payload).encode('utf-8')

                req = urllib.request.Request(
                    'http://localhost:12580/api/download',
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )

                with urllib.request.urlopen(req, timeout=2) as response:
                    print(f"Roxy response: {response.status}")
                return

            # Roxy isn't running.
            # Start it WITHOUT passing the download URL.
            default_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Programs",
                "Roxy",
                "Roxy.exe"
            )

            executable_path = None
            if os.path.exists(default_path):
                executable_path = default_path
            else:
                alt_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "Roxy.exe")
                if os.path.exists(alt_path):
                    executable_path = alt_path

            if not executable_path:
                print(f"Roxy.exe not found at: {default_path}")
                return

            subprocess.Popen(
                [executable_path],
                shell=False,
                cwd=os.path.dirname(executable_path)
            )

            print(f"Roxy.exe launched from: {executable_path}")

            # Wait for API server with faster polling (0.05s intervals)
            # Check ready file first for faster detection
            for i in range(40):  # 40 * 0.05s = 2s max (was 5s)
                time.sleep(0.05)
                # Check ready file first (no network overhead)
                if os.path.exists(ROXY_READY_FILE):
                    # Verify with HTTP check to ensure API is actually ready
                    if self.is_roxy_instance_running():
                        print(f"Roxy API ready after {i * 0.05:.2f}s (detected via ready file)")
                        break
                # Fallback to HTTP check if ready file not yet created
                elif i % 4 == 0:  # Check HTTP every 4th iteration (every 0.2s)
                    if self.is_roxy_instance_running():
                        print(f"Roxy API ready after {i * 0.05:.2f}s (detected via HTTP)")
                        break
            else:
                print("Roxy API did not become available.")
                return

            # Send the COMPLETE request after Roxy is running.
            data = json.dumps(payload).encode('utf-8')

            req = urllib.request.Request(
                'http://localhost:12580/api/download',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=3) as response:
                print(f"Download sent to Roxy: {response.status}")

        except Exception as e:
            print(f"ERROR in open_roxy_with_url: {e}")
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def main():
    PORT = 12579  # Use different port to avoid conflict with Roxy's API
    
    server = HTTPServer(('localhost', PORT), RoxyLauncherHandler)
    print(f"Roxy Launcher Server running on http://localhost:{PORT}")
    print("Waiting for download URLs from Chrome extension...")
    print("Press Ctrl+C to stop the server")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.shutdown()

if __name__ == '__main__':
    main()