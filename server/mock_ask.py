"""Mock /api/ask for building the UI and agent without Grok or Chalk. Standard library only.

Run:   uv run python server/mock_ask.py            (listens on http://localhost:8787)
Test:  curl -s localhost:8787/api/ask -H 'content-type: application/json' -d '{"text":"how crowded is 550 km?"}'
Responses come from docs/mock_ask.json (real tool numbers). Replace this with the real server; keep the shape in docs/api.md.
"""
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANNED = json.loads((ROOT / "docs/mock_ask.json").read_text())


def pick(text: str) -> dict:
    t = text.lower()
    for key, item in CANNED.items():
        if key != "_default" and any(m in t for m in item["match"]):
            return item["response"]
    return CANNED["_default"]["response"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in (("access-control-allow-origin", "*"), ("access-control-allow-headers", "content-type"),
                     ("access-control-allow-methods", "GET, POST, OPTIONS")):
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {"ok": True, "chalk": "mock", "grok": "mock"})
        if self.path == "/api/manifest":
            return self._send(200, json.loads((ROOT / "data/out/manifest.json").read_text()))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/ask":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("content-length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"status": "error", "error": "body must be JSON"})
        self._send(200, pick(str(body.get("text", ""))))


if __name__ == "__main__":
    print("mock /api/ask on http://localhost:8787")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
