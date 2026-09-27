"""Real earnings-call transcripts from the public Hugging Face dataset `kurry/sp500_earnings_transcripts`.

The dataset (MIT licence, "for research and educational use") holds ~33k speaker-segmented transcripts of
S&P 500 / US large-cap calls, 2005 to May 2025. It is used in two steps:

  1. `extract_subset(tickers)` runs one remote DuckDB query against a *pinned* dataset revision and writes
     only the chosen tickers to `data/transcripts/hf_subset.parquet`. The source is a single 1.8 GB Parquet
     file with two row groups, so this streams most of it once; nothing else is kept on disk.
         python -m ingestion.scrapers.hf_transcripts AAPL MSFT JPM ...
  2. `HfTranscriptScraper` reads that local subset, so ingestion afterwards is offline and reproducible.

Each transcript keeps its `{speaker, text}` segments; `normalize.parse_segments` chunks them directly, so
speaker boundaries never depend on regex-parsing names.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

from ingestion.scrapers.base import RawDocument, Scraper

DATASET = "kurry/sp500_earnings_transcripts"
REVISION = "f3ded372da8d18dc6ad98955c4558e34b5fe6d45"  # pinned commit (2025-05-21); change deliberately
SUBSET_PATH = Path(__file__).resolve().parents[2] / "data" / "transcripts" / "hf_subset.parquet"
TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def remote_url(revision: str = REVISION) -> str:
    return f"hf://datasets/{DATASET}@{revision}/parquet_files/part-0.parquet"


def extract_subset(tickers: list[str], out: Path = SUBSET_PATH, revision: str = REVISION) -> int:
    """Copy the given tickers' transcripts from the pinned remote dataset into a local Parquet file."""
    import duckdb

    tickers = sorted({t.upper() for t in tickers})
    bad = [t for t in tickers if not TICKER_RE.match(t)]
    if bad:
        raise ValueError(f"invalid tickers: {bad}")
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    token = os.environ.get("HF_TOKEN")
    if token:  # optional; only reduces rate limiting on this public dataset
        con.execute(f"CREATE SECRET hf_token (TYPE huggingface, TOKEN '{token.replace(chr(39), '')}')")
    in_list = ", ".join(f"'{t}'" for t in tickers)
    con.execute(f"""
        COPY (SELECT symbol, company_name, year, quarter, date, structured_content
              FROM '{remote_url(revision)}' WHERE symbol IN ({in_list}) ORDER BY symbol, date)
        TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
    return con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]


class HfTranscriptScraper(Scraper):
    name = "hf_transcripts"

    def __init__(self, path: Path | None = None):
        self.path = Path(path or SUBSET_PATH)
        self._rows: list[dict] | None = None

    def _load(self) -> list[dict]:
        if self._rows is None:
            if not self.path.exists():
                raise FileNotFoundError(f"{self.path} missing: run `python -m ingestion.scrapers.hf_transcripts <TICKERS>`")
            import duckdb
            cur = duckdb.connect().execute(
                f"SELECT symbol, company_name, year, quarter, date, structured_content FROM '{self.path.as_posix()}'")
            cols = [c[0] for c in cur.description]
            self._rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return self._rows

    def fetch(self, ticker: str, since: dt.date | None = None) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for row in self._load():
            if row["symbol"] != ticker.upper():
                continue
            doc_date = dt.date.fromisoformat(str(row["date"])[:10])
            if since and doc_date < since:
                continue
            segments = [{"speaker": (s.get("speaker") or "").strip(), "text": (s.get("text") or "").strip()}
                        for s in (row["structured_content"] or []) if (s.get("text") or "").strip()]
            if not segments:
                continue
            docs.append(RawDocument(
                ticker=row["symbol"], doc_type="transcript", doc_date=doc_date,
                text="\n".join(f"{s['speaker']}: {s['text']}" for s in segments),
                title=f"{row['company_name']} Q{row['quarter']} {row['year']} Earnings Call",
                source="hf_transcripts", source_url=f"https://huggingface.co/datasets/{DATASET}/tree/{REVISION}",
                meta={"segments": segments},
            ))
        return docs


if __name__ == "__main__":
    import sentari_env  # noqa: F401  (HF_TOKEN from .env)
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: python -m ingestion.scrapers.hf_transcripts TICKER [TICKER ...]")
    n = extract_subset(args)
    print(f"wrote {n} transcripts for {len(set(args))} tickers -> {SUBSET_PATH}")
