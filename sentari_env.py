"""Load settings from a local `.env` file into the process environment.

Imported by every Sentari package's `__init__`, so it runs before any module reads
`os.environ` (several do so at import time). Rules:

* File location: `$SENTARI_ENV_FILE` if set, else `<repo root>/.env`. A missing file is fine.
* Real environment variables always win over the file (`override=False`), so CI, Docker and
  Cloud Run settings are never clobbered by a stray local `.env`.
* `SENTARI_SKIP_DOTENV=1` disables loading (the test-suite sets this so tests never depend on your keys).
* Empty values (`KEY=`) are ignored so `.env.example` can be copied verbatim without blanking real settings.
* Never logs values.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_loaded = False


def env_path() -> Path:
    return Path(os.environ.get("SENTARI_ENV_FILE") or ROOT / ".env")


def _parse(text: str) -> dict[str, str]:
    """Minimal fallback parser (KEY=VALUE, # comments, optional quotes) used only if python-dotenv is absent."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if value[:1] in "\"'" and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        out[key] = value
    return out


def load_env(force: bool = False) -> list[str]:
    """Load the .env file; returns the names of variables that were set from it (never values)."""
    global _loaded
    if (_loaded and not force) or os.environ.get("SENTARI_SKIP_DOTENV") == "1":
        return []
    _loaded = True
    path = env_path()
    if not path.is_file():
        return []
    try:
        from dotenv import dotenv_values
        values = dotenv_values(path)
    except ImportError:
        values = _parse(path.read_text(encoding="utf-8"))
    applied = []
    for key, value in values.items():
        if value is None or value == "" or key in os.environ:
            continue
        os.environ[key] = value
        applied.append(key)
    return applied


load_env()
