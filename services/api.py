# ─────────────────────────────────────────────────────────────
# services/api.py
#
# A fake API service for testing Phantom.
# Reads PORT from environment variable — so Phantom can launch
# multiple copies of this same file on different ports.
#
# Key difference from ProcessPulse workers:
# ProcessPulse workers had hardcoded ports (8001, 8002).
# Phantom services read their port from the environment —
# so the same file can run as replica 1, 2, or 3.
# ─────────────────────────────────────────────────────────────

import os
import time
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# read port from environment — Phantom sets this before launching
PORT = int(os.environ.get("PORT", 8001))


class APIHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            response = json.dumps({
                "status": "ok",
                "service": "api-server",
                "port": PORT
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        elif self.path == "/hello":
            response = json.dumps({
                "message": f"Hello from api-server on port {PORT}"
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_server():
    server = HTTPServer(("localhost", PORT), APIHandler)
    server.serve_forever()


print(f"api-server starting on port {PORT}")

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

# main loop — the actual "work" this service does
count = 0
while True:
    count += 1
    time.sleep(2)