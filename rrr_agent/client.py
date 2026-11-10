"""Ovoko CRM klientas. Užklausos siunčiamos kaip form data, ne JSON."""

from __future__ import annotations

import json
import socket
import ssl
import time
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from urllib import parse

from rrr_agent.config import Settings

_ip_cache: dict[str, tuple[float, str]] = {}


class RrrApiError(Exception):
    def __init__(self, message: str, status_code: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _read_dns_name(data: bytes, offset: int) -> tuple[int, int]:
    hops = 0
    end = offset
    jumped = False
    while offset < len(data) and hops < 12:
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumped:
                end = offset
            return end, offset
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                break
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                end = offset + 2
            offset = pointer
            jumped = True
            hops += 1
            continue
        offset += 1 + length
        if not jumped:
            end = offset
    return end, end


def _ipv4_from_dns(host: str, server: str) -> str | None:
    query_id = int(time.time() * 1000) & 0xFFFF
    header = query_id.to_bytes(2, "big") + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    question = b"".join(bytes([len(part)]) + part.encode("ascii") for part in host.split(".") if part) + b"\x00"
    packet = header + question + b"\x00\x01\x00\x01"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns:
        dns.settimeout(3)
        dns.sendto(packet, (server, 53))
        data, _address = dns.recvfrom(2048)
    if len(data) < 12:
        return None
    offset, _end = _read_dns_name(data, 12)
    offset += 4
    answers = int.from_bytes(data[6:8], "big")
    for _answer in range(answers):
        offset, _end = _read_dns_name(data, offset)
        if offset + 10 > len(data):
            return None
        kind = int.from_bytes(data[offset:offset + 2], "big")
        length = int.from_bytes(data[offset + 8:offset + 10], "big")
        start = offset + 10
        if kind == 1 and length == 4 and start + 4 <= len(data):
            return ".".join(str(part) for part in data[start:start + 4])
        offset = start + length
    return None


def _ipv4(host: str) -> str:
    cached = _ip_cache.get(host)
    now = time.time()
    if cached and now - cached[0] < 600:
        return cached[1]
    for server in ("1.1.1.1", "8.8.8.8"):
        try:
            address = _ipv4_from_dns(host, server)
        except OSError:
            continue
        if address:
            _ip_cache[host] = (now, address)
            return address
    raise RrrApiError("Nepavyko rasti Ovoko adreso. Patikrink internetą ir spausk Kelti dar kartą.")


class _DirectConnection(HTTPSConnection):
    """Jungiasi pagal jau rastą IP, o sertifikatą tikrina pagal tikrąjį vardą."""

    def __init__(self, host: str, ip: str, timeout: float, context: ssl.SSLContext):
        super().__init__(host, timeout=timeout, context=context)
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch_https(url: str, timeout: float = 8, limit: int = 16) -> tuple[int, bytes]:
    """Atsisiunčia per rastą IPv4, nes Windows vardų paieška naujam adresui grąžina 11001."""
    parsed = parse.urlparse(url)
    host = parsed.hostname or ""
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    connection = _DirectConnection(host, _ipv4(host), timeout, ssl.create_default_context())
    try:
        connection.request(
            "GET",
            target,
            headers={"Host": host, "User-Agent": "Mozilla/5.0", "Accept": "*/*"},
        )
        response = connection.getresponse()
        return response.status, response.read(limit)
    finally:
        connection.close()


def form_fields(data: dict[str, Any]) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for key, value in data.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            raise RrrApiError(f"Laukas {key} turi būti skaičius arba tekstas.")
        if isinstance(value, list):
            name = key if key.endswith("[]") else f"{key}[]"
            for item in value:
                if item is None or item == "":
                    continue
                fields.append((name, str(item)))
            continue
        fields.append((key, str(value)))
    return fields


class RrrClient:
    def __init__(self, settings: Settings, timeout: float = 60):
        self.settings = settings
        self.timeout = timeout

    def post(self, path: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        missing = self.settings.missing()
        if missing:
            names = ", ".join(missing)
            raise RrrApiError(f".env trūksta: {names}")

        payload = {
            "username": self.settings.username,
            "password": self.settings.password,
            "user_token": self.settings.user_token,
        }
        if fields:
            payload.update(fields)

        body = parse.urlencode(form_fields(payload)).encode("utf-8")
        url = f"{self.settings.base_url}{path}"
        parsed = parse.urlparse(url)
        host = parsed.hostname or ""
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        try:
            if parsed.scheme == "http":
                connection: HTTPConnection = HTTPConnection(host, port=parsed.port or 80, timeout=self.timeout)
            else:
                connection = _DirectConnection(host, _ipv4(host), self.timeout, ssl.create_default_context())
            connection.request(
                "POST",
                target,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0",
                    "Host": host,
                    "Content-Length": str(len(body)),
                },
            )
            response = connection.getresponse()
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
            connection.close()
        except RrrApiError:
            raise
        except OSError as exc:
            raise RrrApiError("Nepavyko prisijungti prie Ovoko. Patikrink internetą ir spausk Kelti dar kartą.") from exc
        if status >= 400:
            raise RrrApiError(f"Ovoko atsakė HTTP {status}: {raw[:500]}")

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RrrApiError(f"Ovoko grąžino ne JSON: {raw[:500]}") from exc

        if not isinstance(parsed, dict):
            raise RrrApiError("Ovoko atsakymas neturi laukų.", payload=parsed)

        status_code = str(parsed.get("status_code", ""))
        created = status_code == "R200" or (status_code == "R202" and parsed.get("part_id"))
        if not created:
            message = str(parsed.get("msg") or "Ovoko grąžino klaidą")
            raise RrrApiError(message, status_code or None, parsed)
        return parsed
