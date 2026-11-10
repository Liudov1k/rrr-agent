"""Atidaro plakatą ir įrašo naršyklėje padarytas pataisas į plakatas.html."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "plakatas.html"
MAX_BYTES = 2_000_000


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BYTES:
            self.send_error(413)
            return
        data = self.rfile.read(length)
        head = data[:3000].lower()
        if b"<!doctype html>" not in head or b"<html" not in head:
            self.send_error(400)
            return
        TARGET.write_bytes(data)
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 9877), Handler)
    print("Redaguok čia: http://127.0.0.1:9877/plakatas.html")
    server.serve_forever()
