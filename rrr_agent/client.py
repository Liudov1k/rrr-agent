"""Ovoko CRM klientas. Užklausos siunčiamos kaip form data, ne JSON."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request

from rrr_agent.config import Settings


class RrrApiError(Exception):
    def __init__(self, message: str, status_code: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


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
        http_request = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RrrApiError(f"Ovoko atsakė HTTP {exc.code}: {raw[:500]}") from exc
        except error.URLError as exc:
            raise RrrApiError(f"Nepavyko prisijungti prie {url}: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RrrApiError(f"Ovoko grąžino ne JSON: {raw[:500]}") from exc

        if not isinstance(parsed, dict):
            raise RrrApiError("Ovoko atsakymas neturi laukų.", payload=parsed)

        status_code = str(parsed.get("status_code", ""))
        if status_code != "R200":
            message = str(parsed.get("msg") or "Ovoko grąžino klaidą")
            raise RrrApiError(message, status_code or None, parsed)
        return parsed
