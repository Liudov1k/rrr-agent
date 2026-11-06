"""Vietinis langas: viena detalė, keli automobiliai, keli skelbimai."""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from rrr_agent.client import RrrApiError, RrrClient
from rrr_agent.config import Settings, load_settings
from rrr_agent.nuotraukos import content_type, parse_multipart, resolve_photo, save_image
from rrr_agent.skelbimai import publish

PAGE = Path(__file__).with_name("langas.html")
MAX_PHOTO_REQUEST = 40_000_000
MODEL_BRANDS = (80, 103)
DEFAULT_CAR_IDS = ("4", "18", "2")
_garage_cache: dict[str, object] = {"at": 0.0, "cars": []}
_choice_cache: dict[str, object] = {"at": 0.0, "choices": None}


def garage_cars(settings: Settings) -> list[dict[str, str]]:
    """Grąžina Ovoko automobilius su modelio pavadinimu. Sąrašas kelias minutes laikomas atmintyje."""
    if settings.missing():
        return []
    now = time.time()
    cached = _garage_cache.get("cars")
    if isinstance(cached, list) and cached and now - float(_garage_cache["at"]) < 300:
        return cached

    client = RrrClient(settings)
    names: dict[str, str] = {}
    for brand_id in MODEL_BRANDS:
        for item in client.post(f"/get/car_models/{brand_id}").get("list") or []:
            model_id = str(item.get("id") or "")
            name = str(item.get("name") or "").strip()
            if model_id and name:
                names[model_id] = name

    cars: list[dict[str, str]] = []
    for item in client.post("/v2/get/cars", {"page": 1}).get("data") or []:
        car_id = str(item.get("id") or "").strip()
        if not car_id:
            continue
        model = names.get(str(item.get("car_model") or ""))
        years = str(item.get("car_years") or "").strip()
        if model:
            title = f"Land Rover {model} {years}".strip()
        else:
            title = f"Automobilis {car_id}" + (f", {years}" if years else "")
        cars.append({"id": car_id, "pavadinimas": title, "metai": years})
    cars.sort(key=lambda car: car["pavadinimas"])
    _garage_cache["at"] = now
    _garage_cache["cars"] = cars
    return cars


def _choice_rows(payload: dict) -> list[dict[str, str]]:
    items = payload.get("list") or {}
    rows: list[dict[str, str]] = []
    if isinstance(items, dict):
        pairs = items.items()
    elif isinstance(items, list):
        pairs = ((item.get("id"), item) for item in items if isinstance(item, dict))
    else:
        pairs = ()
    for key, value in pairs:
        if isinstance(value, dict):
            label = str(value.get("lt") or value.get("en") or value.get("name") or "").strip()
        else:
            label = str(value).strip()
        if label:
            rows.append({"id": str(key), "pavadinimas": label})
    rows.sort(key=lambda row: (row["id"] != "0", int(row["id"]) if row["id"].isdigit() else row["id"]))
    return rows


def _category_path(item: dict, by_id: dict[str, dict]) -> str:
    names: list[str] = []
    current: dict | None = item
    seen: set[str] = set()
    while current:
        current_id = str(current.get("id") or "")
        if not current_id or current_id in seen:
            break
        seen.add(current_id)
        label = str(current.get("lt") or current.get("en") or "").strip()
        if label:
            names.append(label)
        parent_id = str(current.get("parent_id") or "")
        current = by_id.get(parent_id) if parent_id not in ("", "0") else None
    return " › ".join(reversed(names))


def choice_lists(settings: Settings) -> dict[str, list[dict[str, str]]]:
    """Ovoko pasirinkimai: visos 3 lygio kategorijos, kokybė, pozicija ir vairo pusė."""
    if settings.missing():
        return {"kategorijos": [], "kokybe": [], "pozicijos": [], "vairas": []}
    now = time.time()
    cached = _choice_cache.get("choices")
    if isinstance(cached, dict) and now - float(_choice_cache["at"]) < 600:
        return cached

    client = RrrClient(settings)
    raw_categories = client.post("/get/categories").get("list") or []
    by_id = {str(item.get("id")): item for item in raw_categories if isinstance(item, dict)}
    categories = [
        {"id": str(item.get("id")), "pavadinimas": _category_path(item, by_id)}
        for item in raw_categories
        if isinstance(item, dict) and str(item.get("level")) == "3" and item.get("id")
    ]
    categories.sort(key=lambda row: row["pavadinimas"].casefold())
    choices = {
        "kategorijos": categories,
        "kokybe": _choice_rows(client.post("/get/part_quality")),
        "pozicijos": _choice_rows(client.post("/get/part_position")),
        "vairas": _choice_rows(client.post("/get/wheel")),
    }
    _choice_cache["at"] = now
    _choice_cache["choices"] = choices
    return choices


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
        if path == "/api/sarasai":
            try:
                self._json(200, choice_lists(load_settings()))
            except RrrApiError as exc:
                self._json(400, {"klaida": str(exc), "kategorijos": [], "kokybe": [], "pozicijos": [], "vairas": []})
            return
        if path == "/api/automobiliai":
            try:
                cars = garage_cars(load_settings())
            except RrrApiError as exc:
                self._json(400, {"klaida": str(exc), "automobiliai": [], "numatytieji": []})
                return
            chosen = [car_id for car_id in DEFAULT_CAR_IDS if any(car["id"] == car_id for car in cars)]
            self._json(200, {"automobiliai": cars, "numatytieji": chosen})
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
