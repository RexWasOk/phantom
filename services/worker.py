import os
import time
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 9001))


class WorkerHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            response = json.dumps({
                "status": "ok",
                "service": "worker",
                "port": PORT
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
    server = HTTPServer(("localhost", PORT), WorkerHandler)
    server.serve_forever()


print(f"worker starting on port {PORT}")

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

count = 0
while True:
    count += 1
    time.sleep(3)