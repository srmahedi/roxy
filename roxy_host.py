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
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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
            with urllib.request.urlopen(req, timeout=2) as response:
                is_running = (response.status == 200)
                if is_running:
                    print("✓ Roxy instance detected via HTTP API on port 12580")
                else:
                    print("✗ Roxy API responded but not ready")
                return is_running
        except Exception as e:
            print(f"✗ HTTP API check failed: {e}")
            return False
    
    def is_roxy_instance_running_with_retry(self, retries=3, delay=1):
        """Check if Roxy instance is running with retry logic"""
        for i in range(retries):
            if self.is_roxy_instance_running():
                return True
            if i < retries - 1:
                print(f"Retrying Roxy detection in {delay}s... (attempt {i+2}/{retries})")
                time.sleep(delay)
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

            if self.is_roxy_instance_running_with_retry(retries=2, delay=0.5):
                print("Roxy is running - sending full download information")
                data = json.dumps(payload).encode('utf-8')

                req = urllib.request.Request(
                    'http://localhost:12580/api/download',
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )

                with urllib.request.urlopen(req, timeout=10) as response:
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

            # Wait for API server
            for _ in range(20):
                time.sleep(0.5)
                if self.is_roxy_instance_running():
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

            with urllib.request.urlopen(req, timeout=10) as response:
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