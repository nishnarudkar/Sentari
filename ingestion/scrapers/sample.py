"""Offline scraper reading bundled synthetic fixtures from data/sample/.

File naming: <TICKER>_<doc_type>_<YYYY-MM-DD>.txt  (first line: "TITLE: ...").
The fixtures are SYNTHETIC (fictional companies) so the whole pipeline can be
demoed and tested without network access or third-party licensing.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ingestion.scrapers.base import RawDocument, Scraper

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


class SampleScraper(Scraper):
    name = "sample"

    def __init__(self, directory: Path | None = None):
        self.directory = directory or SAMPLE_DIR

    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for path in sorted(self.directory.glob(f"{ticker.upper()}_*.txt")):
            parts = path.stem.split("_")
            if len(parts) < 3:
                continue
            _, doc_type, date_s = parts[0], parts[1], parts[2]
            doc_date = dt.date.fromisoformat(date_s)
            if since and doc_date < since:
                continue
            body = path.read_text(encoding="utf-8")
            title = ""
            if body.startswith("TITLE:"):
                first, _, body = body.partition("\n")
                title = first[len("TITLE:"):].strip()
            docs.append(RawDocument(
                ticker=ticker.upper(), doc_type=doc_type, doc_date=doc_date, text=body,
                title=title, source="sample", source_url=f"file://{path.name}",
            ))
        return docs
