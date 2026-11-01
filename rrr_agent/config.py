"""Nuskaito Ovoko prisijungimą iš .env, neatskleisdamas slaptažodžio."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "rrr_agent").is_dir() and (candidate / ".env").exists():
            return candidate
    for candidate in (cwd, *cwd.parents):
        if (candidate / "rrr_agent").is_dir():
            return candidate
    return cwd


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str, file_values: dict[str, str], default: str = "") -> str:
    from_env = os.environ.get(name)
    if from_env:
        return from_env.strip()
    return file_values.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    user_token: str
    base_url: str

    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.username:
            missing.append("RRR_USERNAME")
        if not self.password:
            missing.append("RRR_PASSWORD")
        if not self.user_token:
            missing.append("RRR_USER_TOKEN")
        return missing


def load_settings() -> Settings:
    root = project_root()
    file_values = _read_env_file(root / ".env")
    base_url = _setting("RRR_API_BASE_URL", file_values, "https://api.rrr.lt")
    return Settings(
        username=_setting("RRR_USERNAME", file_values),
        password=_setting("RRR_PASSWORD", file_values),
        user_token=_setting("RRR_USER_TOKEN", file_values),
        base_url=base_url.rstrip("/"),
    )
