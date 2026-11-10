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
from urllib import request

from rrr_agent.nuotraukos import content_type

_URL = re.compile(r"https://[A-Za-z0-9.-]+\.(?:localhost\.run|lhr\.life|trycloudflare\.com)")


def _photo_handler(files: dict[str, Path], hits: list[str]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _file(self) -> Path | None:
            name = Path(self.path.split("?", 1)[0]).name
            path = files.get(name)
            if path is None or not path.is_file():
                hits.append(f"{self.command} {self.path} missing")
                return None
            return path

        def _send(self, include_body: bool) -> None:
            path = self._file()
            if path is None:
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type(path))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(data)
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
            if _URL.search("".join(chunks)):
                return

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
        command = [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
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


def _wait_until_fetchable(base: str, files: dict[str, Path]) -> None:
    name = next(iter(files))
    url = f"{base.rstrip('/')}/{name}"
    deadline = time.time() + 30
    last_error = "nuotrauka dar nepasiekiama"
    while time.time() < deadline:
        try:
            http_request = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with request.urlopen(http_request, timeout=10) as response:
                data = response.read(3)
            if data[:3] in {b"\xff\xd8\xff", b"\x89PN", b"RIF"}:
                time.sleep(8)
                return
            last_error = "adresas grąžino ne nuotrauką"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    raise ValueError(f"Ovoko nepasiekė nuotraukos. {last_error}")


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
        _wait_until_fetchable(base, files)
        yield base
    finally:
        _stop(proc)
        server.shutdown()
        server.server_close()
