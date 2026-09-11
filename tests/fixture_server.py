"""A tiny local web server that serves a fixture site directory.

Fixture files contain the literal token `127.0.0.1:PORT` wherever an absolute
URL is needed (canonicals, sitemap entries, robots Sitemap directives). The
handler rewrites that token to the real host and port at serve time, so the
fixtures stay readable and portable while the audit sees a coherent origin.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def make_handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FixtureServer/1.0"

        def log_message(self, *args):        # keep test output clean
            pass

        def _resolve(self):
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path.endswith("/"):
                path += "index.html"
            if path == "":
                path = "/index.html"
            target = (root / path.lstrip("/")).resolve()
            if not str(target).startswith(str(root.resolve())):
                return None                  # no path traversal out of the fixture
            if target.is_dir():
                target = target / "index.html"
            return target if target.is_file() else None

        def do_GET(self):
            target = self._resolve()
            if target is None:
                body = b"<html><body><h1>404 Not Found</h1></body></html>"
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            text = target.read_text(encoding="utf-8")
            text = text.replace("127.0.0.1:PORT",
                                f"{self.server.server_address[0]}:{self.server.server_address[1]}")
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            target = self._resolve()
            self.send_response(200 if target else 404)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(target.suffix, "text/html")
                             if target else "text/html")
            self.end_headers()

    return Handler


class FixtureSite:
    """Context manager serving a fixture directory on an ephemeral port."""

    def __init__(self, directory: str | Path):
        self.root = Path(directory).resolve()
        self.httpd = None
        self.thread = None

    def __enter__(self) -> str:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.root))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address[0], self.httpd.server_address[1]
        return f"http://{host}:{port}/"

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        return False
