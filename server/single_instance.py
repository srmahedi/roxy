"""
Single Instance Management for preventing multiple app instances
"""
import socket
import json
import threading
import os
from utils.constants import SINGLE_INSTANCE_PORT


class SingleInstanceManager:
    """Manages single instance functionality for the application."""
    
    def __init__(self, port=SINGLE_INSTANCE_PORT):
        self.port = port
        self.socket = None
        self.is_first_instance = False
        
    def acquire_lock(self):
        """Try to acquire the single instance lock."""
        try:
            # Try to bind to the port - if successful, we're the first instance
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('localhost', self.port))
            self.socket.listen(5)
            self.is_first_instance = True
            return True
        except socket.error:
            # Port is already in use - another instance is running
            self.is_first_instance = False
            return False
    
    def send_to_running_instance(self, url: str, filename: str = None):
        """Send URL to the already running instance."""
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('localhost', self.port))
            # Send as JSON to include both URL and filename
            data = json.dumps({'url': url, 'filename': filename})
            client.send(data.encode('utf-8'))
            client.close()
            return True
        except Exception as e:
            print(f"Failed to send to running instance: {e}")
            return False
    
    def listen_for_connections(self, callback):
        """Listen for connections from other instances."""
        if not self.is_first_instance or not self.socket:
            return
            
        def listener():
            while True:
                try:
                    client, address = self.socket.accept()
                    data = client.recv(1024)
                    if data:
                        try:
                            # Try to parse as JSON first
                            payload = json.loads(data.decode('utf-8'))
                            url = payload.get('url')
                            filename = payload.get('filename')
                            callback(url, filename)
                        except json.JSONDecodeError:
                            # Fallback to simple string (old format)
                            url = data.decode('utf-8')
                            callback(url, None)
                    client.close()
                except Exception as e:
                    print(f"Error in single instance listener: {e}")
                    break
        
        thread = threading.Thread(target=listener, daemon=True)
        thread.start()
    
    def release_lock(self):
        """Release the single instance lock."""
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except:
                pass
