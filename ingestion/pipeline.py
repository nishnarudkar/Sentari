"""Idempotent ingestion: fetch -> dedupe -> normalize -> chunk -> persist.

Re-running for the same tickers never duplicates rows: documents are keyed by a
hash of their normalized text, and chunk (document_id, idx) is unique.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingestion.normalize import content_hash, normalize_text, parse_plain, parse_transcript
from ingestion.scrapers.base import RawDocument, Scraper
from storage.models import Chunk, Document

log = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).with_name("scheduler_config.yaml")


@dataclass
class IngestStats:
    fetched: int = 0
    new_documents: int = 0
    duplicates: int = 0
    chunks: int = 0
    failures: list[str] = field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_scrapers(names: list[str]) -> list[Scraper]:
    from ingestion.scrapers.news import NewsRssScraper
    from ingestion.scrapers.nse import NseScraper
    from ingestion.scrapers.sample import SampleScraper
    from ingestion.scrapers.sec_edgar import SecEdgarScraper

    registry = {"sample": SampleScraper, "sec_edgar": SecEdgarScraper,
                "news_rss": NewsRssScraper, "nse": NseScraper}
    return [registry[n]() for n in names if n in registry]


def chunk_document(doc: RawDocument):
    if doc.doc_type == "transcript":
        return parse_transcript(doc.text)
    section = "mdna" if doc.doc_type in ("10-K", "10-Q") else "body"
    return parse_plain(doc.text, section=section)


def store_document(session: Session, doc: RawDocument, stats: IngestStats) -> Document | None:
    text = normalize_text(doc.text)
    if len(text) < 20:
        return None
    # ticker is part of the hash so identical boilerplate across tickers is not merged
    digest = content_hash(f"{doc.ticker}|{doc.doc_type}|{text}")
    if session.scalar(select(Document.id).where(Document.content_hash == digest)) is not None:
        stats.duplicates += 1
        return None
    drafts = chunk_document(doc)
    record = Document(
        ticker=doc.ticker, doc_type=doc.doc_type, doc_date=doc.doc_date, title=doc.title,
        source=doc.source, source_url=doc.source_url, content_hash=digest,
        chunks=[Chunk(idx=d.idx, text=d.text, section=d.section, speaker=d.speaker) for d in drafts],
    )
    session.add(record)
    session.flush()
    stats.new_documents += 1
    stats.chunks += len(drafts)
    return record


def ingest(session: Session, tickers: list[str], scrapers: list[Scraper],
           since: dt.date | None = None, retries: int = 2) -> IngestStats:
    stats = IngestStats()
    for ticker in tickers:
        for scraper in scrapers:
            for attempt in range(retries + 1):
                try:
                    docs = scraper.fetch(ticker, since)
                    break
                except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
                    log.warning("%s/%s attempt %d failed: %s", scraper.name, ticker, attempt + 1, exc)
                    if attempt == retries:
                        stats.failures.append(f"{scraper.name}:{ticker}:{exc}")
                        docs = []
                    else:
                        time.sleep(2 ** attempt)
            stats.fetched += len(docs)
            for doc in docs:
                store_document(session, doc, stats)
    session.commit()
    return stats


def run_from_config(session: Session, config: dict | None = None) -> IngestStats:
    cfg = config or load_config()
    since = None
    if cfg.get("lookback_days"):
        since = dt.date.today() - dt.timedelta(days=int(cfg["lookback_days"]))
    return ingest(session, cfg["watchlist"], build_scrapers(cfg["sources"]), since=since)
