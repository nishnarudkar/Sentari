"""News fetcher over public RSS feeds (Google News RSS query by ticker/company)."""
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ingestion.scrapers.base import RawDocument, Scraper, cached_get

RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


class NewsRssScraper(Scraper):
    name = "news_rss"

    def __init__(self, company_names: dict[str, str] | None = None, limit: int = 15):
        self.company_names = company_names or {}
        self.limit = limit

    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        query = f"{self.company_names.get(ticker.upper(), ticker)} stock earnings"
        xml_text = cached_get(RSS.format(q=quote_plus(query)), ttl_hours=6)
        root = ET.fromstring(xml_text)
        docs: list[RawDocument] = []
        for item in root.iterfind(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc_html = item.findtext("description") or ""
            desc = BeautifulSoup(desc_html, "lxml").get_text(" ").strip()
            try:
                pub = parsedate_to_datetime(item.findtext("pubDate") or "").date()
            except (TypeError, ValueError):
                pub = dt.date.today()
            if since and pub < since:
                continue
            docs.append(RawDocument(
                ticker=ticker.upper(), doc_type="news", doc_date=pub,
                text=f"{title}. {desc}", title=title, source="news_rss", source_url=link,
            ))
            if len(docs) >= self.limit:
                break
        return docs
