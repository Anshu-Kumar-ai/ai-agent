"""
Local Browser Test Server
Simple HTTP server to serve test fixtures for browser validation.
"""
import http.server
import socketserver
import os
import threading
import time
from pathlib import Path

# Serve from the fixtures/browser directory
FIXTURE_DIR = Path(__file__).parent  # This script is already in tests/fixtures/browser/
PORT = 8765

class TestFixtureHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FIXTURE_DIR), **kwargs)
    
    def log_message(self, format, *args):
        # Suppress default log messages
        pass

def start_server():
    """Start the test fixture server in a background thread."""
    os.chdir(FIXTURE_DIR)
    with socketserver.TCPServer(("", PORT), TestFixtureHandler) as httpd:
        print(f"Test fixture server running on http://localhost:{PORT}")
        httpd.serve_forever()

def get_server_url(path="index.html"):
    """Get the full URL for a test fixture."""
    return f"http://localhost:{PORT}/{path}"

if __name__ == "__main__":
    start_server()