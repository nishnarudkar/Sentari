"""Scraper interface and a polite, cached HTTP client."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

USER_AGENT = os.environ.get("SENTARI_USER_AGENT", "Sentari research project (contact: set SENTARI_USER_AGENT)")
CACHE_DIR = Path(os.environ.get("SENTARI_CACHE_DIR", "data/cache"))


@dataclass
class RawDocument:
    ticker: str
    doc_type: str
    doc_date: dt.date
    text: str
    title: str = ""
    source: str = ""
    source_url: str = ""
    meta: dict = field(default_factory=dict)


class Scraper(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        """Return documents for ticker published on/after `since`."""


def cached_get(url: str, *, params: dict | None = None, headers: dict | None = None,
               min_interval: float = 0.2, retries: int = 3, ttl_hours: float = 24.0) -> str:
    """GET with an on-disk cache of raw responses (so parsing bugs never cost a re-fetch)
    plus exponential-backoff retries. Raw payloads are cached *before* parsing (project.md risks)."""
    import requests

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((url + repr(sorted((params or {}).items()))).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.txt"
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl_hours * 3600:
        return path.read_text(encoding="utf-8")

    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            time.sleep(min_interval)
            resp = requests.get(url, params=params, headers=hdrs, timeout=30)
            if resp.status_code in (429, 503):
                raise RuntimeError(f"rate limited ({resp.status_code})")
            resp.raise_for_status()
            path.write_text(resp.text, encoding="utf-8")
            return resp.text
        except Exception as exc:  # noqa: BLE001 - retry any transient failure
            last_exc = exc
            wait = 2 ** attempt
            log.warning("GET %s failed (%s); retry in %ss", url, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries} attempts") from last_exc
