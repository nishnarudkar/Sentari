"""SEC EDGAR fetcher for 10-K / 10-Q MD&A sections (official API; no scraping of HTML search).

Set SENTARI_USER_AGENT to "Name email@example.com" - SEC requires a contact UA.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from bs4 import BeautifulSoup

from ingestion.scrapers.base import RawDocument, Scraper, cached_get

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"

MDNA_START = re.compile(r"item\s*[27]\.?\s*management.s discussion and analysis", re.IGNORECASE)
MDNA_END = re.compile(r"item\s*(?:3|4|7a|8)\.?\s*(?:quantitative|controls|financial statements|"
                      r"changes in and disagreements)", re.IGNORECASE)


def extract_mdna(html: str, max_chars: int = 200_000) -> str:
    """Pull the MD&A section out of a filing's HTML; falls back to full text."""
    text = BeautifulSoup(html, "lxml").get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n", text)
    starts = [m.start() for m in MDNA_START.finditer(text)]
    if not starts:
        return text[:max_chars]
    # the last "Item 7 ... MD&A" heading is usually the body, earlier ones the table of contents
    start = starts[-1] if len(starts) > 1 else starts[0]
    m_end = MDNA_END.search(text, start + 200)
    end = m_end.start() if m_end else start + max_chars
    return text[start:end][:max_chars]


class SecEdgarScraper(Scraper):
    name = "sec_edgar"

    def __init__(self, forms: tuple[str, ...] = ("10-K", "10-Q")):
        self.forms = forms
        self._cik_map: dict[str, str] | None = None

    def _cik(self, ticker: str) -> str | None:
        if self._cik_map is None:
            data = json.loads(cached_get(TICKER_MAP_URL, ttl_hours=24 * 7))
            self._cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
        return self._cik_map.get(ticker.upper())

    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        cik = self._cik(ticker)
        if not cik:
            return []
        subs = json.loads(cached_get(SUBMISSIONS_URL.format(cik=cik)))
        recent = subs.get("filings", {}).get("recent", {})
        docs: list[RawDocument] = []
        for form, date_s, acc, primary in zip(
            recent.get("form", []), recent.get("filingDate", []),
            recent.get("accessionNumber", []), recent.get("primaryDocument", []),
        ):
            if form not in self.forms:
                continue
            filed = dt.date.fromisoformat(date_s)
            if since and filed < since:
                continue
            url = ARCHIVE_URL.format(cik_int=int(cik), acc_nodash=acc.replace("-", ""), doc=primary)
            html = cached_get(url, ttl_hours=24 * 30)
            docs.append(RawDocument(
                ticker=ticker.upper(), doc_type=form, doc_date=filed, text=extract_mdna(html),
                title=f"{ticker.upper()} {form} {date_s} - MD&A", source="sec_edgar", source_url=url,
            ))
        return docs
