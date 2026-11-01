"""Komandinė eilutė Ovoko prekių agentui.

Pavyzdžiai:
  python -m rrr_agent busena
  python -m rrr_agent nauja prekes/bamperis.json
  python -m rrr_agent tikrinti prekes/pavyzdys.json
  python -m rrr_agent kelti prekes/pavyzdys.json --be-siuntimo
  python -m rrr_agent sarasas kategorijos --ieskoti zibint
  python -m rrr_agent langas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rrr_agent.client import RrrApiError, RrrClient
from rrr_agent.config import load_settings, project_root
from rrr_agent.preke import TEMPLATE, car_payload, check_draft, load_draft, part_payload, save_draft

LISTS = {
    "kategorijos": "/get/categories",
    "kokybe": "/get/part_quality",
    "detales-busenos": "/get/part_status",
    "auto-busenos": "/get/car_status",
    "markes": "/get/car_brands",
    "modeliai": "/get/car_models/{brand_id}",
    "kuras": "/get/fuel",
    "kebulai": "/get/car_body_type",
    "pavaros": "/get/wheel_drive",
    "dezes": "/get/gearbox_type",
    "vairas": "/get/wheel",
    "pozicijos": "/get/part_position",
}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def _print_issues(errors: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"Įspėjimas: {warning}")
    for error in errors:
        print(f"Klaida: {error}")


def _rows(payload: dict) -> list[tuple[str, str]]:
    items = payload.get("list", [])
    rows: list[tuple[str, str]] = []
    if isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, dict):
                label = str(value.get("lt") or value.get("en") or value.get("name") or "")
            else:
                label = str(value)
            rows.append((str(key), label))
        return rows
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                rows.append(("", str(item)))
                continue
            label = str(item.get("lt") or item.get("name") or item.get("en") or "")
            if item.get("year_start"):
                label = f"{label} ({item.get('year_start')}-{item.get('year_end') or ''})"
            if item.get("level"):
                label = f"L{item['level']} {label}"
            rows.append((str(item.get("id", "")), label))
    return rows


def command_busena() -> int:
    settings = load_settings()
    print(f"API adresas: {settings.base_url}")
    print(f"Projektas: {project_root()}")
    for name, present in (
        ("RRR_USERNAME", bool(settings.username)),
        ("RRR_PASSWORD", bool(settings.password)),
        ("RRR_USER_TOKEN", bool(settings.user_token)),
    ):
        print(f"{name}: {'įrašytas' if present else 'tuščias'}")
    missing = settings.missing()
    if missing:
        print("Kelti į Ovoko galėsi, kai šiuos laukus užpildysi .env faile: " + ", ".join(missing))
        print("Juodraštį ruošti ir tikrinti galima jau dabar.")
        return 0
    print("Prisijungimas užpildytas. Galima kelti detales.")
    return 0


def command_nauja(path: Path) -> int:
    if path.exists():
        print(f"Failas jau yra: {path}")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    save_draft(path, TEMPLATE)
    print(f"Sukurtas juodraštis: {path}")
    return 0


def command_tikrinti(path: Path) -> int:
    try:
        draft = load_draft(path)
        errors, warnings = check_draft(draft)
    except ValueError as exc:
        print(f"Klaida: {exc}")
        return 1
    _print_issues(errors, warnings)
    if errors:
        return 1
    print(f"{path} paruoštas siuntimui.")
    return 0


def command_kelti(path: Path, dry_run: bool) -> int:
    try:
        draft = load_draft(path)
        errors, warnings = check_draft(draft)
    except ValueError as exc:
        print(f"Klaida: {exc}")
        return 1
    _print_issues(errors, warnings)
    if errors:
        return 1

    car = car_payload(draft)
    part = part_payload(draft)
    if dry_run:
        if car:
            print("Būtų siunčiamas automobilis:")
            print(json.dumps(car, ensure_ascii=False, indent=2))
        else:
            print("Automobilis jau turi ovoko_id arba jo šiame faile nėra. Būtų naudojamas esamas car_id.")
        print("Būtų siunčiama detalė:")
        print(json.dumps(part, ensure_ascii=False, indent=2))
        print("Į užklausą dar būtų pridėti username, password ir user_token iš .env.")
        return 0

    settings = load_settings()
    missing = settings.missing()
    if missing:
        print("Siuntimas sustabdytas. .env trūksta: " + ", ".join(missing))
        print("Juodraštis patikrintas. Kai Ovoko atsiųs prisijungimą, paleisk šią pačią komandą dar kartą.")
        return 2

    client = RrrClient(settings)
    try:
        if car:
            created = client.post("/crm/importCar", car)
            car_id = created.get("car_id")
            draft.setdefault("automobilis", {})["ovoko_id"] = car_id
            save_draft(path, draft)
            print(f"Automobilis įkeltas. car_id={car_id}")
        if draft.get("detale", {}).get("ovoko_id"):
            print(f"Detalė jau įkelta. part_id={draft['detale']['ovoko_id']}")
            return 0
        created_part = client.post("/crm/importPart", part_payload(draft))
        part_id = created_part.get("part_id")
        draft.setdefault("detale", {})["ovoko_id"] = part_id
        save_draft(path, draft)
        print(f"Detalė įkelta. part_id={part_id}")
    except RrrApiError as exc:
        code = f" ({exc.status_code})" if exc.status_code else ""
        print(f"Ovoko klaida{code}: {exc}")
        return 1
    return 0


def command_sarasas(name: str, query: str, brand_id: int | None) -> int:
    path = LISTS[name]
    if name == "modeliai":
        if brand_id is None:
            print("Modeliams reikia markės ID: python -m rrr_agent sarasas modeliai --marke 3")
            return 1
        path = path.format(brand_id=brand_id)

    settings = load_settings()
    missing = settings.missing()
    if missing:
        print("Sąrašui iš Ovoko reikia prisijungimo. .env trūksta: " + ", ".join(missing))
        return 2

    try:
        payload = RrrClient(settings).post(path)
    except RrrApiError as exc:
        code = f" ({exc.status_code})" if exc.status_code else ""
        print(f"Ovoko klaida{code}: {exc}")
        return 1

    needle = query.casefold()
    shown = 0
    for item_id, label in _rows(payload):
        line = f"{item_id}\t{label}".rstrip()
        if needle and needle not in line.casefold():
            continue
        print(line)
        shown += 1
    if shown == 0:
        print("Nieko nerasta.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ovoko (RRR) prekių kėlimo agentas.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("busena", help="Parodo, ar .env prisijungimas užpildytas.")

    new_parser = sub.add_parser("nauja", help="Sukuria tuščią prekės juodraštį.")
    new_parser.add_argument("failas", type=Path)

    check_parser = sub.add_parser("tikrinti", help="Patikrina juodraštį nesiunčiant į Ovoko.")
    check_parser.add_argument("failas", type=Path)

    upload_parser = sub.add_parser("kelti", help="Įkelia automobilį ir detalę į Ovoko.")
    upload_parser.add_argument("failas", type=Path)
    upload_parser.add_argument(
        "--be-siuntimo",
        action="store_true",
        help="Parodo, ką siųstų, bet į Ovoko nesijungia.",
    )

    list_parser = sub.add_parser("sarasas", help="Atsisiunčia Ovoko ID sąrašą.")
    list_parser.add_argument("pavadinimas", choices=sorted(LISTS))
    list_parser.add_argument("--ieskoti", default="", help="Filtruoja eilutes pagal tekstą.")
    list_parser.add_argument("--marke", type=int, help="Markės ID, reikalingas modeliams.")

    sub.add_parser("langas", help="Atidaro langą, kuriame ta pati dalis keliama keliems automobiliams.")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    if args.command == "busena":
        return command_busena()
    if args.command == "nauja":
        return command_nauja(args.failas)
    if args.command == "tikrinti":
        return command_tikrinti(args.failas)
    if args.command == "kelti":
        return command_kelti(args.failas, args.be_siuntimo)
    if args.command == "sarasas":
        return command_sarasas(args.pavadinimas, args.ieskoti, args.marke)
    if args.command == "langas":
        from rrr_agent.server import serve

        serve()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
