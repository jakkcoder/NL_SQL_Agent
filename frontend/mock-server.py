#!/usr/bin/env python3
"""Optional mock chat API for local testing. Run: python mock-server.py"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json

PORT = 8000


class ChatHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path not in ("/chat", "/"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        message = data.get("message") or data.get("query") or ""
        reply = f'Echo: {message}' if message else "Send a message field named 'message'."

        body = json.dumps({"reply": reply}).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), ChatHandler)
    print(f"Mock chat API: http://localhost:{PORT}/chat")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
