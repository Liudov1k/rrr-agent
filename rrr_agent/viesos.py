"""Laikinas nuotraukų adresas, kurį Ovoko serveris gali atsisiųsti kėlimo metu."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rrr_agent.client import fetch_https
from rrr_agent.nuotraukos import content_type, photos_dir

_URL = re.compile(r"https://[A-Za-z0-9.-]+\.(?:localhost\.run|lhr\.life|trycloudflare\.com)")
_PROBE = b"\xff\xd8\xff\xd9"
_bridge_lock = threading.Lock()
_bridge: dict[str, object] = {"base": "", "proc": None}


def _photo_handler(files: dict[str, Path] | None = None, hits: list[str] | None = None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _file(self) -> Path | bytes | None:
            name = Path(self.path.split("?", 1)[0]).name
            if name == "probe.jpg":
                return _PROBE
            path = files.get(name) if files is not None else None
            if path is None and files is None:
                root = photos_dir().resolve()
                candidate = (root / name).resolve()
                if root in candidate.parents and candidate.is_file() and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    path = candidate
            if path is None or not path.is_file():
                if hits is not None:
                    hits.append(f"{self.command} {self.path} missing")
                return None
            return path

        def _send(self, include_body: bool) -> None:
            found = self._file()
            if found is None:
                self.send_error(404)
                return
            data = found if isinstance(found, bytes) else found.read_bytes()
            kind = "image/jpeg" if isinstance(found, bytes) else content_type(found)
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(data)
            if hits is not None:
                hits.append(f"{self.command} {self.path} 200")

        def do_HEAD(self) -> None:
            self._send(False)

        def do_GET(self) -> None:
            self._send(True)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _spawn(command: list[str]) -> subprocess.Popen[str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=flags,
    )


def _wait_for_url(proc: subprocess.Popen[str], timeout: float) -> str:
    chunks: list[str] = []

    def read() -> None:
        if proc.stdout is None:
            return
        while True:
            piece = proc.stdout.read(1)
            if not piece:
                return
            chunks.append(piece)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = "".join(chunks)
        match = _URL.search(text)
        if match:
            return match.group(0).rstrip(".,)")
        if proc.poll() is not None and not thread.is_alive():
            break
        time.sleep(0.2)
    text = "".join(chunks).strip()
    tail = text[-180:] if text else "nėra adreso"
    raise ValueError(f"Ovoko nepasiekė nuotraukų. {tail}")


def _cloudflared_path() -> str | None:
    local = Path.home() / "AppData" / "Local" / "rrr-agent" / "cloudflared.exe"
    if local.is_file():
        return str(local)
    return shutil.which("cloudflared")


def _open_tunnel(port: int) -> tuple[subprocess.Popen[str], str]:
    cloudflared = _cloudflared_path()
    ssh = shutil.which("ssh")
    if cloudflared:
        command = [
            cloudflared,
            "--edge-ip-version",
            "4",
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--no-autoupdate",
        ]
    elif ssh:
        command = [
            ssh,
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "UserKnownHostsFile=NUL",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "BatchMode=yes",
            "-R",
            f"80:127.0.0.1:{port}",
            "nokey@localhost.run",
        ]
    else:
        raise ValueError("Šiame kompiuteryje nėra būdo perduoti nuotrauką Ovoko.")
    proc = _spawn(command)
    try:
        return proc, _wait_for_url(proc, 40)
    except Exception:
        proc.terminate()
        raise


def _probe_ready(base: str) -> bool:
    try:
        status, data = fetch_https(f"{base.rstrip('/')}/probe.jpg", timeout=8, limit=3)
    except Exception:
        return False
    return status == 200 and data.startswith(b"\xff\xd8")


def _wait_until_fetchable(base: str, seconds: float = 45) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _probe_ready(base):
            return
        time.sleep(1)
    raise ValueError("Nuotraukos adresas dar nepasiekiamas. Palauk kelias sekundes ir spausk Kelti dar kartą.")


def ensure_photo_base() -> str:
    """Vienas nuotraukų ryšys visam langui, kad kiekviena kita prekė nekeltų jo iš naujo."""
    with _bridge_lock:
        proc = _bridge.get("proc")
        base = str(_bridge.get("base") or "")
        alive = base and isinstance(proc, subprocess.Popen) and proc.poll() is None
        if not alive:
            if isinstance(proc, subprocess.Popen):
                _stop(proc)
            server = ThreadingHTTPServer(("127.0.0.1", 0), _photo_handler())
            port = int(server.server_address[1])
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                opened, ready = _open_tunnel(port)
            except Exception:
                server.shutdown()
                server.server_close()
                raise
            _bridge["base"] = ready
            _bridge["proc"] = opened
            _bridge["server"] = server
            base = ready
        if not _probe_ready(base):
            _wait_until_fetchable(base, 20 if alive else 45)
        return base


def _stop(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@contextmanager
def temporary_public_base(files: dict[str, Path]) -> Iterator[str | None]:
    if not files:
        yield None
        return
    hits: list[str] = []
    temporary_public_base.hits = hits  # type: ignore[attr-defined]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _photo_handler(files, hits))
    port = int(server.server_address[1])
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    proc: subprocess.Popen[str] | None = None
    try:
        proc, base = _open_tunnel(port)
        _wait_until_fetchable(base)
        yield base
    finally:
        _stop(proc)
        server.shutdown()
        server.server_close()
