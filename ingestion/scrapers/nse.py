"""NSE/BSE corporate-filings fetcher.

NSE's public JSON endpoints require a browser-like session cookie and their ToS
restricts automated access, so this scraper is intentionally conservative:
it only reads the announcements endpoint after priming the cookie, honours the
shared cache/retry client, and returns [] on any access failure rather than
attempting to circumvent blocking. Prefer BSE's official API or company IR pages
for production use (project.md section 12: respect robots.txt / ToS).
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from ingestion.scrapers.base import RawDocument, Scraper, cached_get

log = logging.getLogger(__name__)
ANNOUNCEMENTS = "https://www.nseindia.com/api/corporate-announcements"


class NseScraper(Scraper):
    name = "nse"

    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        try:
            raw = cached_get(ANNOUNCEMENTS, params={"index": "equities", "symbol": ticker.upper()},
                             headers={"Accept": "application/json"}, retries=2, ttl_hours=6)
            items = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning("NSE fetch for %s unavailable (%s); skipping", ticker, exc)
            return []
        docs: list[RawDocument] = []
        for it in items:
            try:
                d = dt.datetime.strptime(it.get("an_dt", "")[:11], "%d-%b-%Y").date()
            except ValueError:
                continue
            if since and d < since:
                continue
            text = (it.get("desc") or "") + ". " + (it.get("attchmntText") or "")
            docs.append(RawDocument(
                ticker=ticker.upper(), doc_type="nse_filing", doc_date=d, text=text,
                title=it.get("desc", ""), source="nse", source_url=it.get("attchmntFile", ""),
            ))
        return docs
