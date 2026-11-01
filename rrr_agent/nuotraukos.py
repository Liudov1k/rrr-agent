"""Iš telefono atsiųstos nuotraukos saugomos šiame kompiuteryje."""

from __future__ import annotations

import uuid
from pathlib import Path

from rrr_agent.config import project_root

MAX_BYTES = 12_000_000
TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def photos_dir() -> Path:
    folder = project_root() / "prekes" / "nuotraukos"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def image_extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_image(data: bytes, folder: Path | None = None) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError("Nuotrauka per didelė. Didžiausias dydis yra 12 MB.")
    extension = image_extension(data)
    if extension is None:
        raise ValueError("Tinka JPG, PNG arba WEBP nuotrauka.")
    target = folder or photos_dir()
    target.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{extension}"
    (target / name).write_bytes(data)
    return f"/nuotraukos/{name}"


def resolve_photo(url_path: str, folder: Path | None = None) -> Path:
    name = Path(url_path).name
    if not name or name != url_path.rstrip("/").split("/")[-1] or ".." in url_path:
        raise ValueError("Neteisingas nuotraukos adresas.")
    root = (folder or photos_dir()).resolve()
    path = (root / name).resolve()
    if root not in path.parents:
        raise ValueError("Neteisingas nuotraukos adresas.")
    if path.suffix.lower().lstrip(".") not in {"jpg", "jpeg", "png", "webp"}:
        raise ValueError("Neteisingas nuotraukos adresas.")
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def content_type(path: Path) -> str:
    return TYPES.get(path.suffix.lower().lstrip(".").replace("jpeg", "jpg"), "application/octet-stream")


def parse_multipart(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("Nuotrauka nepridėta.")
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("Nuotrauka nepridėta.")
    delimiter = b"--" + boundary.encode("utf-8")
    files: list[tuple[str, bytes]] = []
    for chunk in body.split(delimiter):
        if b"\r\n\r\n" not in chunk:
            continue
        head, data = chunk.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        header = head.decode("utf-8", errors="replace")
        if "filename=" not in header.lower():
            continue
        filename = "nuotrauka"
        for line in header.split("\r\n"):
            if "filename=" in line.lower():
                filename = line.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"')
        if data:
            files.append((filename, data))
    if not files:
        raise ValueError("Pasirink bent vieną nuotrauką.")
    return files
