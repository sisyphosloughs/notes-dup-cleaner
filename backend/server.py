import http.server
import json
import shutil
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from backend.scanner import SKIP_DIRS

STATIC_DIR = Path(__file__).parent.parent / "static"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
}


class Handler(http.server.BaseHTTPRequestHandler):
    payload: dict = {}
    root: Path = Path(".")

    def log_message(self, fmt, *args):
        pass  # stille Logs

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            body = (STATIC_DIR / "index.html").read_bytes()
            self._send(200, MIME[".html"], body)

        elif parsed.path.startswith("/static/"):
            filename = parsed.path[len("/static/"):]
            fpath = STATIC_DIR / filename
            suffix = fpath.suffix.lower()
            if fpath.is_file() and suffix in MIME:
                self._send(200, MIME[suffix], fpath.read_bytes())
            else:
                self._send(404, "text/plain", b"Not found")

        elif parsed.path == "/data":
            self._send(200, "application/json",
                       json.dumps(self.payload).encode())

        elif parsed.path == "/file":
            qs   = urllib.parse.parse_qs(parsed.query)
            path = qs.get("path", [""])[0]
            try:
                content = Path(path).read_text(encoding="utf-8", errors="replace")
                body = json.dumps({"content": content, "path": path}).encode()
                self._send(200, "application/json", body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self._send(500, "application/json", body)

        elif parsed.path == "/folders":
            folders = sorted(
                str(d.relative_to(self.root))
                for d in self.root.rglob("*")
                if d.is_dir() and not any(s in d.parts for s in SKIP_DIRS)
            )
            self._send(200, "application/json",
                       json.dumps(folders).encode())

        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/delete":
            length  = int(self.headers.get("Content-Length", 0))
            body    = json.loads(self.rfile.read(length))
            deleted, failed = 0, 0
            for p in body.get("paths", []):
                try:
                    Path(p).unlink()
                    deleted += 1
                except Exception as e:
                    print(f"  Fehler: {p}: {e}")
                    failed += 1
            self._send(200, "application/json",
                       json.dumps({"deleted": deleted, "failed": failed}).encode())

        elif self.path == "/move":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            src      = Path(body.get("path", ""))
            dest_dir = Path(body.get("dest", ""))
            try:
                if not src.is_file():
                    raise FileNotFoundError(f"Quelldatei nicht gefunden: {src}")
                if not dest_dir.is_dir():
                    raise NotADirectoryError(f"Zielordner nicht gefunden: {dest_dir}")
                stem    = src.stem
                suffix  = src.suffix
                target  = dest_dir / src.name
                counter = 1
                while target.exists():
                    target = dest_dir / f"{stem}-{counter}{suffix}"
                    counter += 1
                shutil.move(str(src), str(target))
                self._send(200, "application/json",
                           json.dumps({"ok": True, "dest": str(target)}).encode())
            except Exception as e:
                self._send(500, "application/json",
                           json.dumps({"ok": False, "error": str(e)}).encode())

        elif self.path == "/save":
            length  = int(self.headers.get("Content-Length", 0))
            body    = json.loads(self.rfile.read(length))
            fpath   = Path(body.get("path", ""))
            content = body.get("content", "")
            try:
                if not fpath.is_file():
                    raise FileNotFoundError(f"Datei nicht gefunden: {fpath}")
                fpath.resolve().relative_to(self.root.resolve())
                fpath.write_text(content, encoding="utf-8")
                self._send(200, "application/json",
                           json.dumps({"ok": True}).encode())
            except Exception as e:
                self._send(500, "application/json",
                           json.dumps({"ok": False, "error": str(e)}).encode())

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def serve(payload: dict, root: Path, port: int):
    Handler.payload = payload
    Handler.root    = root

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    url    = f"http://127.0.0.1:{port}"
    print(f"\nBrowser oeffnet sich unter: {url}")
    print("Strg+C zum Beenden.\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
