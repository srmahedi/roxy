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
                
                if url:
                    print(f"Received download URL: {url}")
                    print(f"URL type: {type(url)}")
                    print(f"URL length: {len(url)}")
                    if filename:
                        print(f"Received filename: {filename}")
                    
                    # Open Roxy.exe with the URL and filename
                    self.open_roxy_with_url(url, filename)
                    
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
    
    def send_url_to_roxy(self, url, filename=None, retries=3, delay=0.5):
        """Send URL to existing Roxy instance via HTTP API with retry logic"""
        for i in range(retries):
            try:
                payload = {'url': url}
                if filename:
                    payload['filename'] = filename
                
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    'http://localhost:12580/api/download',
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        print(f"✓ URL sent to Roxy instance successfully (attempt {i+1})")
                        return True
                    else:
                        print(f"✗ Roxy API returned status {response.status} (attempt {i+1})")
            except Exception as e:
                print(f"✗ HTTP API method failed (attempt {i+1}): {e}")
            
            if i < retries - 1:
                print(f"Retrying in {delay}s...")
                time.sleep(delay)
        
        print(f"✗ All {retries} attempts failed to send URL to Roxy")
        return False
    
    def open_roxy_with_url(self, url, filename=None):
        """Open Roxy.exe with the given URL and optional filename"""
        try:
            print("=" * 50)
            print(f"Processing download URL: {url}")
            if filename:
                print(f"Filename: {filename}")
            print("=" * 50)
            
            # STRICT CHECK: Only communicate if Roxy is running with retry logic
            roxy_is_running = self.is_roxy_instance_running_with_retry(retries=2, delay=0.5)
            
            if roxy_is_running:
                # Roxy IS running - ONLY communicate via HTTP API, NEVER launch
                print("✓ Roxy is running - sending URL to existing instance via HTTP API")
                if self.send_url_to_roxy(url, filename, retries=3, delay=0.3):
                    print("✓ SUCCESS: URL sent to existing Roxy instance via HTTP API")
                    return
                else:
                    print("✗ FAILED: Could not communicate with running Roxy instance")
                    print("  Roxy is running but HTTP API communication failed")
                    print("  NOT launching new instance to avoid conflicts")
                    return
            else:
                # Roxy is NOT running - launch new instance
                print("✗ Roxy is NOT running - launching new instance")
                
                # Try dynamic path based on current user's home directory
                default_path = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Roxy", "Roxy.exe")
                
                try:
                    # Pass URL and filename as command line arguments
                    args = [default_path, url]
                    if filename:
                        args.append(f"--filename={filename}")
                    subprocess.Popen(args, shell=True)
                    print(f"✓ Launched Roxy.exe from: {default_path}")
                    print(f"✓ URL passed as argument: {url}")
                    if filename:
                        print(f"✓ Filename passed as argument: {filename}")
                    
                    # Give Roxy a moment to start
                    time.sleep(2)
                    return
                except FileNotFoundError:
                    print(f"✗ Roxy.exe not found at: {default_path}")
                    
                    # If not in default location, try PATH
                    try:
                        args = ['Roxy.exe', url]
                        if filename:
                            args.append(f"--filename={filename}")
                        subprocess.Popen(args, shell=True)
                        print("✓ Launched Roxy.exe from PATH")
                        print(f"✓ URL passed as argument: {url}")
                        if filename:
                            print(f"✓ Filename passed as argument: {filename}")
                        time.sleep(2)
                        return
                    except FileNotFoundError:
                        print("✗ Roxy.exe not found in PATH")
                        print("ERROR: Roxy.exe not found. Please ensure it exists at:")
                        print(f"  {default_path}")
                        print("Or add Roxy.exe to your system PATH")
                        return
            
        except Exception as e:
            print(f"✗ ERROR in open_roxy_with_url: {e}")
    
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