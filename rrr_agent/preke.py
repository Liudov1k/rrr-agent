"""Juodraščio tikrinimas prieš siuntimą į Ovoko."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CAR_FIELDS = {
    "car_model",
    "car_years",
    "status",
    "car_class",
    "car_engine_cubic_capacity",
    "car_engine_power",
    "car_gearbox_type",
    "car_fuel",
    "car_mileage",
    "car_body_type",
    "car_wheel_type",
    "car_wheel_drive",
    "photo",
    "photos",
    "external_id",
    "place",
    "car_color",
    "car_color_code",
    "car_body_number",
    "car_engine_code",
    "car_gearbox_code",
    "original_currency",
    "defectation_notes",
}

PART_FIELDS = {
    "category_id",
    "car_id",
    "quality",
    "status",
    "mechanic",
    "position",
    "notes",
    "place",
    "manufacturer_code",
    "visible_code",
    "other_code",
    "optional_codes",
    "external_id",
    "internal_notes",
    "price",
    "original_currency",
    "weight",
    "length",
    "width",
    "height",
    "photo",
    "photos",
    "sticker_note",
    "english",
}

LOCAL_KEYS = {"ovoko_id"}

TEMPLATE: dict[str, Any] = {
    "_paaiskinimas": (
        "Užpildyk skaičius, kuriuos Ovoko naudoja viduje. "
        "Kai turėsi API raktą, ID sąrašus gausi komanda: python -m rrr_agent sarasas kategorijos. "
        "Detalė parduotuvėje matoma, kai yra kaina didesnė už 0 ir nuotraukos URL. "
        "Nuotrauka turi būti vieša nuoroda, ne failas iš kompiuterio."
    ),
    "automobilis": {
        "external_id": "auto-1",
        "car_model": None,
        "car_years": "2016",
        "status": None,
        "car_fuel": None,
        "car_mileage": None,
        "place": "",
        "ovoko_id": None,
    },
    "detale": {
        "external_id": "detale-1",
        "category_id": None,
        "quality": None,
        "status": None,
        "price": 0,
        "original_currency": "EUR",
        "manufacturer_code": "",
        "notes": "",
        "place": "",
        "photo": "",
        "photos": [],
        "ovoko_id": None,
    },
}


def load_draft(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} nėra tvarkingas JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} turi būti objektas su laukais automobilis ir detale.")
    return data


def save_draft(path: Path, draft: dict[str, Any]) -> None:
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _section(draft: dict[str, Any], name: str) -> dict[str, Any]:
    value = draft.get(name) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Laukas {name} turi būti objektas.")
    return value


def _unknown_keys(section: dict[str, Any], allowed: set[str]) -> list[str]:
    return sorted(
        key
        for key in section
        if not key.startswith("_") and key not in allowed and key not in LOCAL_KEYS
    )


def _copy_fields(section: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in allowed:
        if key not in section:
            continue
        value = section[key]
        if value is None or value == "" or value == []:
            continue
        payload[key] = value
    return payload


def _normalize_photos(payload: dict[str, Any]) -> None:
    photos = payload.get("photos") or []
    if isinstance(photos, str):
        photos = [photos]
    photo = payload.get("photo")
    if photo and photo not in photos:
        photos = [photo, *photos]
    elif photos and not photo:
        payload["photo"] = photos[0]
    if photos:
        payload["photos"] = photos


def _is_http_url(value: str) -> bool:
    return (
        value.startswith("https://")
        or value.startswith("http://")
        or value.startswith("/nuotraukos/")
    )


def check_draft(draft: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if "detale" not in draft:
        return ["Trūksta objekto detale."], warnings

    try:
        part = _section(draft, "detale")
        car = _section(draft, "automobilis") if "automobilis" in draft else {}
    except ValueError as exc:
        return [str(exc)], warnings

    unknown_part = _unknown_keys(part, PART_FIELDS)
    if unknown_part:
        errors.append("Detalėje nežinomi laukai: " + ", ".join(unknown_part))
    if car:
        unknown_car = _unknown_keys(car, CAR_FIELDS)
        if unknown_car:
            errors.append("Automobilyje nežinomi laukai: " + ", ".join(unknown_car))

    for field in ("category_id", "quality", "status"):
        if part.get(field) in (None, ""):
            errors.append(f"Detalei trūksta {field}.")

    has_car_id = part.get("car_id") not in (None, "") or car.get("ovoko_id") not in (None, "")
    if not has_car_id:
        for field in ("car_model", "car_years", "status"):
            if car.get(field) in (None, ""):
                errors.append(
                    f"Automobiliui trūksta {field}. Arba į detale.car_id įrašyk jau esamo Ovoko automobilio ID."
                )

    price = part.get("price")
    if price in (None, "", 0, 0.0):
        warnings.append("Kaina tuščia arba 0. Ovoko detalę į parduotuvę įdės tik su kaina, didesne už 0.")
    elif isinstance(price, bool) or not isinstance(price, (int, float)):
        errors.append("Kaina turi būti skaičius.")
    elif price < 0:
        errors.append("Kaina negali būti neigiama.")

    currency = part.get("original_currency") or car.get("original_currency")
    if currency not in (None, "", "EUR", "PLN"):
        errors.append("original_currency gali būti EUR arba PLN.")

    photo_values: list[str] = []
    if part.get("photo"):
        photo_values.append(str(part["photo"]))
    extra_photos = part.get("photos") or []
    if isinstance(extra_photos, str):
        extra_photos = [extra_photos]
    if not isinstance(extra_photos, list):
        errors.append("photos turi būti nuorodų sąrašas.")
    else:
        photo_values.extend(str(item) for item in extra_photos if item)

    if not photo_values:
        warnings.append("Nėra nuotraukos. Be jos detalė parduotuvėje nematoma.")
    for url in photo_values:
        if not _is_http_url(url):
            errors.append(f"Nuotrauka turi būti įkelta iš telefono arba http nuoroda: {url}")

    return errors, warnings


def car_payload(draft: dict[str, Any]) -> dict[str, Any] | None:
    if "automobilis" not in draft:
        return None
    car = _section(draft, "automobilis")
    if car.get("ovoko_id"):
        return None
    payload = _copy_fields(car, CAR_FIELDS)
    _normalize_photos(payload)
    return payload or None


def part_payload(draft: dict[str, Any]) -> dict[str, Any]:
    part = _section(draft, "detale")
    payload = _copy_fields(part, PART_FIELDS)
    car = _section(draft, "automobilis") if "automobilis" in draft else {}
    if "car_id" not in payload and car.get("ovoko_id"):
        payload["car_id"] = car["ovoko_id"]
    _normalize_photos(payload)
    return payload
