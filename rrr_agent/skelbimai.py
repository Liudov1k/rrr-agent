"""Iš vienos detalės paruošia atskirą skelbimą kiekvienam automobiliui."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from rrr_agent.client import RrrApiError, RrrClient
from rrr_agent.config import Settings, project_root
from rrr_agent.preke import car_payload, check_draft, load_draft, part_payload, save_draft

_TRANSLIT = str.maketrans(
    {
        "ą": "a",
        "č": "c",
        "ę": "e",
        "ė": "e",
        "į": "i",
        "š": "s",
        "ų": "u",
        "ū": "u",
        "ž": "z",
    }
)


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _integer(value: Any, label: str) -> int | None:
    if _blank(value) or value is False:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} turi būti sveikasis skaičius.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if not text.lstrip("-").isdigit():
        raise ValueError(f"{label} turi būti sveikasis skaičius.")
    return int(text)


def _number(value: Any, label: str) -> int | float | None:
    if _blank(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{label} turi būti skaičius.")
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None
        try:
            parsed = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} turi būti skaičius.") from exc
        return int(parsed) if parsed.is_integer() else parsed
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slug(value: str) -> str:
    cleaned = []
    for char in value.casefold().translate(_TRANSLIT):
        if char.isalnum():
            cleaned.append(char)
        elif char in " -_":
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "auto"


def _part_fields(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Dalies duomenys turi būti objektai.")
    photos = raw.get("photos") or []
    if isinstance(photos, str):
        photos = [line.strip() for line in photos.splitlines() if line.strip()]
    if not isinstance(photos, list):
        raise ValueError("Nuotraukos turi būti sąrašas.")

    optional_codes = raw.get("optional_codes") or []
    if isinstance(optional_codes, str):
        optional_codes = [line.strip() for line in optional_codes.splitlines() if line.strip()]

    part: dict[str, Any] = {
        "category_id": _integer(raw.get("category_id"), "Kategorija"),
        "quality": _integer(raw.get("quality"), "Kokybė"),
        "status": _integer(raw.get("status"), "Būsena"),
        "position": _integer(raw.get("position"), "Dalies pozicija"),
        "price": _number(raw.get("price"), "Kaina"),
        "original_currency": _text(raw.get("original_currency")) or "EUR",
        "manufacturer_code": _text(raw.get("manufacturer_code")),
        "visible_code": _text(raw.get("visible_code")),
        "other_code": _text(raw.get("other_code")),
        "optional_codes": [str(item).strip() for item in optional_codes if str(item).strip()],
        "notes": _text(raw.get("notes")),
        "internal_notes": _text(raw.get("internal_notes")),
        "place": _text(raw.get("place")),
        "sticker_note": _text(raw.get("sticker_note")),
        "photo": _text(raw.get("photo")),
        "photos": [str(item).strip() for item in photos if str(item).strip()],
    }
    if str(raw.get("english")).strip() == "1":
        part["english"] = 1
    return {key: value for key, value in part.items() if not _blank(value)}


def _apply_dimensions(part: dict[str, Any], dims: Any) -> dict[str, Any]:
    if not isinstance(dims, dict):
        return part
    labels = (
        ("svoris", "svoris", "kg"),
        ("ilgis", "ilgis", "cm"),
        ("plotis", "plotis", "cm"),
        ("aukstis", "aukštis", "cm"),
    )
    pieces: list[str] = []
    clean: dict[str, str] = {}
    for key, label, unit in labels:
        value = _text(dims.get(key)).replace(",", ".")
        if not value:
            continue
        clean[key] = value
        pieces.append(f"{label} {value} {unit}")
    if not pieces:
        return part
    line = "Matmenys: " + ", ".join(pieces) + "."
    notes = part.get("internal_notes") or ""
    part["internal_notes"] = f"{notes}\n{line}".strip() if notes else line
    part["_matmenys"] = clean
    return part


def build_drafts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Sukuria po vieną juodraštį kiekvienam automobiliui. Dalies laukai visuose vienodi."""
    cars = payload.get("automobiliai")
    if not isinstance(cars, list) or not cars:
        raise ValueError("Pridėk bent vieną automobilį.")
    if len(cars) > 30:
        raise ValueError("Vienu kartu galima kurti ne daugiau kaip 30 skelbimų.")

    part = _apply_dimensions(_part_fields(payload.get("detale") or {}), payload.get("matmenys"))
    base_code = _slug(_text((payload.get("detale") or {}).get("external_id")) or _text(part.get("manufacturer_code")) or "dalis")
    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()
    drafts: list[dict[str, Any]] = []

    for index, raw_car in enumerate(cars, start=1):
        if not isinstance(raw_car, dict):
            raise ValueError(f"{index} automobilis užpildytas neteisingai.")
        title = _text(raw_car.get("pavadinimas")) or f"Automobilis {index}"
        car_id = _integer(raw_car.get("car_id"), f"{title} ID")
        car_model = _integer(raw_car.get("car_model"), f"{title} modelis")
        car_years = _text(raw_car.get("car_years"))
        car_status = _integer(raw_car.get("status"), f"{title} būsena")

        if car_id is not None:
            if car_id in seen_ids:
                raise ValueError(f"Automobilis {title} pasirinktas dukart.")
            seen_ids.add(car_id)
        elif car_model is None or not car_years or car_status is None:
            raise ValueError(
                f"{title}: įrašyk Ovoko automobilio ID arba modelio ID, metus ir būseną."
            )

        slug = _slug(title)
        if slug in seen_slugs:
            slug = f"{slug}-{index}"
        seen_slugs.add(slug)

        detale = dict(part)
        detale["external_id"] = f"{base_code}-{slug}"
        draft: dict[str, Any] = {
            "_pavadinimas": title,
            "detale": detale,
        }
        if car_id is not None:
            detale["car_id"] = car_id
        else:
            draft["automobilis"] = {
                "external_id": f"auto-{slug}",
                "car_model": car_model,
                "car_years": car_years,
                "status": car_status,
                "ovoko_id": None,
            }

        errors, _warnings = check_draft(draft)
        if errors:
            raise ValueError(f"{title}: " + " ".join(errors))
        drafts.append(draft)

    return drafts


def save_drafts(drafts: list[dict[str, Any]], root: Path | None = None) -> list[dict[str, str]]:
    folder = (root or project_root()) / "prekes" / "partijos" / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, str]] = []
    for index, draft in enumerate(drafts, start=1):
        title = str(draft.get("_pavadinimas") or f"auto-{index}")
        path = folder / f"{index:02d}-{_slug(title)}.json"
        save_draft(path, draft)
        saved.append({"pavadinimas": title, "failas": str(path)})
    return saved


def upload_draft(path: Path, client: RrrClient) -> dict[str, Any]:
    draft = load_draft(path)
    errors, _warnings = check_draft(draft)
    if errors:
        raise RrrApiError("; ".join(errors))

    car = car_payload(draft)
    if car:
        created = client.post("/crm/importCar", car)
        draft.setdefault("automobilis", {})["ovoko_id"] = created.get("car_id")
        save_draft(path, draft)

    if draft.get("detale", {}).get("ovoko_id"):
        return {"part_id": draft["detale"]["ovoko_id"], "jau_buvo": True}

    created_part = client.post("/crm/importPart", part_payload(draft))
    part_id = created_part.get("part_id")
    draft.setdefault("detale", {})["ovoko_id"] = part_id
    save_draft(path, draft)
    car_id = draft.get("detale", {}).get("car_id") or draft.get("automobilis", {}).get("ovoko_id")
    return {"part_id": part_id, "car_id": car_id}


def _require_public_photos(draft: dict[str, Any]) -> None:
    part = draft.get("detale") or {}
    photos = []
    if part.get("photo"):
        photos.append(str(part["photo"]))
    photos.extend(str(item) for item in part.get("photos") or [])
    if any(url.startswith("/nuotraukos/") for url in photos):
        raise ValueError(
            "Telefono nuotrauka išsaugota kompiuteryje, bet Ovoko jos iš namų Wi-Fi atsisiųsti negali. "
            "Skelbimas paruoštas, į Ovoko su šia nuotrauka dar neiškeltas."
        )


def publish(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    drafts = build_drafts(payload)
    saved = save_drafts(drafts)
    result: dict[str, Any] = {
        "kiekis": len(saved),
        "skelbimai": saved,
    }
    missing = settings.missing()
    if not missing:
        for draft in drafts:
            _require_public_photos(draft)
    if missing:
        result["rezimas"] = "juodrastis"
        result["zinute"] = (
            "Skelbimai paruošti šiame kompiuteryje. "
            "Į Ovoko jie iškeliaus, kai .env užpildysi: " + ", ".join(missing) + "."
        )
        return result

    client = RrrClient(settings)
    uploaded = []
    for item in saved:
        created = upload_draft(Path(item["failas"]), client)
        uploaded.append({**item, **created})
    result["rezimas"] = "ovoko"
    result["skelbimai"] = uploaded
    result["zinute"] = f"Į Ovoko įkelta skelbimų: {len(uploaded)}."
    return result
