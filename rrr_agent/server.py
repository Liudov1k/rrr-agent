"""Vietinis langas: viena detalė, keli automobiliai, keli skelbimai."""

from __future__ import annotations

import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from rrr_agent.client import RrrApiError
from rrr_agent.config import load_settings
from rrr_agent.nuotraukos import content_type, parse_multipart, resolve_photo, save_image
from rrr_agent.skelbimai import publish

PAGE = Path(__file__).with_name("langas.html")
MAX_PHOTO_REQUEST = 40_000_000


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            page = PAGE.read_text(encoding="utf-8").encode("utf-8")
            self._send(200, page, "text/html; charset=utf-8")
            return
        if path == "/api/busena":
            settings = load_settings()
            missing = settings.missing()
            port = self.server.server_address[1]
            self._json(
                200,
                {
                    "prijungta": not missing,
                    "truksta": missing,
                    "telefono_adresai": [f"http://{ip}:{port}/" for ip in lan_addresses()],
                },
            )
            return
        if path.startswith("/nuotraukos/"):
            try:
                photo = resolve_photo(path)
            except (ValueError, FileNotFoundError):
                self._json(404, {"klaida": "Nuotraukos nėra."})
                return
            self._send(200, photo.read_bytes(), content_type(photo))
            return
        self._json(404, {"klaida": "Tokio adreso nėra."})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/nuotraukos":
            self._save_photos()
            return
        if path != "/api/skelbimai":
            self._json(404, {"klaida": "Tokio adreso nėra."})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self._json(413, {"klaida": "Užklausa per didelė."})
            return
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._json(400, {"klaida": "Nusiųsk JSON."})
            return
        if not isinstance(payload, dict):
            self._json(400, {"klaida": "Nusiųsk objekto duomenis."})
            return
        try:
            result = publish(payload, load_settings())
        except (ValueError, RrrApiError) as exc:
            self._json(400, {"klaida": str(exc)})
            return
        self._json(200, result)

    def _save_photos(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_PHOTO_REQUEST:
            self._json(413, {"klaida": "Nuotrauka per didelė arba nepridėta."})
            return
        body = self.rfile.read(length)
        try:
            files = parse_multipart(self.headers.get("Content-Type", ""), body)
            urls = [save_image(data) for _name, data in files[:12]]
        except ValueError as exc:
            self._json(400, {"klaida": str(exc)})
            return
        self._json(200, {"nuotraukos": urls})


def lan_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in addresses if ip and not ip.startswith("127."))


def serve(host: str = "0.0.0.0", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Kompiuteryje atidaryta: http://127.0.0.1:{port}/")
    phone_urls = [f"http://{ip}:{port}/" for ip in lan_addresses()]
    if phone_urls:
        print("Telefone, tame pačiame Wi-Fi, atidaryk:")
        for url in phone_urls:
            print(f"  {url}")
    else:
        print("Telefono adreso nematau. Prijunk kompiuterį prie Wi-Fi ir paleisk dar kartą.")
    print("Kol naudoji telefoną, šio lango neuždaryk. Baigęs paspausk Ctrl+C.")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Langas uždarytas.")
    finally:
        server.server_close()
