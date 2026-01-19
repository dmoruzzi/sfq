#!/usr/bin/env python3
"""
Simple HTTP server to serve test credentials for Grafana Cloud telemetry testing
"""

import http.server
import socketserver
import json
import threading
import time
import os

class CredentialsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve credentials JSON"""
        if self.path == '/creds.json':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            credentials = {
                "url": "https://logs-prod-001.grafana.net/loki/api/v1/push",
                "USER_ID": 1234567,
                "API_KEY": "glc_test_api_key_for_development"
            }
            
            self.wfile.write(json.dumps(credentials, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

def run_server():
    """Run credentials server in background"""
    PORT = 8765
    
    with socketserver.TCPServer(("", PORT), CredentialsHandler) as httpd:
        print(f"Serving credentials on port {PORT}")
        print(f"URL: http://localhost:{PORT}/creds.json")
        httpd.serve_forever()

def main():
    """Main function"""
    print("Starting test credentials server...")
    print("This server provides mock Grafana Cloud credentials for testing")
    print()
    
    # Start server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Give server time to start
    time.sleep(1)
    
    print("Server started successfully!")
    print("You can now run the telemetry example with:")
    print(f"SFQ_GRAFANACLOUD_URL=http://localhost:8765/creds.json")
    print()
    print("Press Ctrl+C to stop the server")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServer stopped")

if __name__ == "__main__":
    main()