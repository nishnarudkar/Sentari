"""Signal validity check (project.md 7.4).

Question: does the prepared-remarks-vs-Q&A sentiment delta correlate with subsequent price movement
(post-earnings drift) better than raw document-level sentiment?

For each transcript event we build three predictors from the stored aspect scores:
    delta      : mean over aspects of (Q&A mean - prepared mean)         <- the platform's signature signal
    doc_level  : plain mean of all aspect scores in the document          <- the naive comparator
    prepared   : mean of prepared-remarks scores only
and correlate each with the forward return (default: 5-trading-day cumulative return after the call date,
market-adjusted when a benchmark is available).

INPUT: forward returns must come from real prices. Provide a CSV with columns `ticker,date,ret_5d`
(date = earnings call date, ret_5d as a decimal), or use --fetch to download prices with yfinance.
There is deliberately NO bundled returns file: the sample corpus is synthetic, so any "correlation"
computed from it would be meaningless.

Reported honestly: n, Spearman rho + p-value, Pearson r, bootstrap 95% CI, and the difference between the
delta and doc-level correlations. With the small n a typical watchlist gives, a null result is the
expected outcome and is reported as such (project.md 11: "a clearly reasoned null result is a legitimate finding").

    python -m evaluation.signal_validity --returns data/returns.csv
    python -m evaluation.signal_validity --fetch --benchmark SPY
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import random
from pathlib import Path

from scipy import stats
from sqlalchemy import select

from absa_service.signals import document_level_sentiment, document_aspect_summary, transcript_delta
from storage.db import get_engine, make_session_factory
from storage.models import Document

OUT = Path("artifacts/results/signal_validity.json")


def build_events(session, model_name: str | None = None) -> list[dict]:
    events = []
    for doc in session.scalars(select(Document).where(Document.doc_type == "transcript").order_by(Document.doc_date)):
        summ = document_aspect_summary(session, doc.id, model_name)
        prepared = [v["prepared"] for v in summ.values() if v["prepared"] is not None]
        events.append({
            "ticker": doc.ticker, "date": doc.doc_date,
            "delta": transcript_delta(session, doc.id, model_name),
            "doc_level": document_level_sentiment(session, doc.id, model_name),
            "prepared": round(sum(prepared) / len(prepared), 4) if prepared else None,
        })
    return events


def load_returns(path: Path) -> dict[tuple[str, dt.date], float]:
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        out[(r["ticker"].upper(), dt.date.fromisoformat(r["date"]))] = float(r["ret_5d"])
    return out


def fetch_returns(events: list[dict], benchmark: str | None = "SPY", horizon: int = 5) -> dict:
    import yfinance as yf  # optional dependency
    out = {}
    for e in events:
        start, end = e["date"] - dt.timedelta(days=5), e["date"] + dt.timedelta(days=horizon * 2 + 6)
        px = yf.download(e["ticker"], start=start, end=end, progress=False, auto_adjust=True)["Close"].squeeze()
        px = px[px.index.date >= e["date"]]
        if len(px) <= horizon:
            continue
        ret = float(px.iloc[horizon] / px.iloc[0] - 1)
        if benchmark:
            bx = yf.download(benchmark, start=start, end=end, progress=False, auto_adjust=True)["Close"].squeeze()
            bx = bx[bx.index.date >= e["date"]]
            if len(bx) > horizon:
                ret -= float(bx.iloc[horizon] / bx.iloc[0] - 1)
        out[(e["ticker"], e["date"])] = ret
    return out


def _bootstrap_ci(x, y, n_boot=2000, seed=0):
    rng, n, vals = random.Random(seed), len(x), []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        xs, ys = [x[i] for i in idx], [y[i] for i in idx]
        if len(set(xs)) > 1 and len(set(ys)) > 1:
            vals.append(stats.spearmanr(xs, ys)[0])
    if len(vals) < 50:
        return (None, None)
    vals.sort()
    return (round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals))], 3))


def correlate(events: list[dict], returns: dict) -> dict:
    rows = [(e, returns[(e["ticker"], e["date"])]) for e in events if (e["ticker"], e["date"]) in returns]
    result: dict = {"n_events": len(rows), "predictors": {}}
    for name in ("delta", "doc_level", "prepared"):
        pairs = [(e[name], r) for e, r in rows if e[name] is not None]
        if len(pairs) < 3:
            result["predictors"][name] = {"n": len(pairs), "note": "too few events"}
            continue
        x, y = zip(*pairs)
        rho, p = stats.spearmanr(x, y)
        r, pr = stats.pearsonr(x, y) if len(set(x)) > 1 and len(set(y)) > 1 else (float("nan"), float("nan"))
        lo, hi = _bootstrap_ci(list(x), list(y))
        result["predictors"][name] = {
            "n": len(pairs), "spearman_rho": None if math.isnan(rho) else round(float(rho), 3),
            "spearman_p": None if math.isnan(p) else round(float(p), 4),
            "pearson_r": None if math.isnan(r) else round(float(r), 3), "bootstrap_ci95_spearman": [lo, hi],
        }
    d, b = result["predictors"].get("delta", {}), result["predictors"].get("doc_level", {})
    if d.get("spearman_rho") is not None and b.get("spearman_rho") is not None:
        result["delta_minus_doc_level_rho"] = round(d["spearman_rho"] - b["spearman_rho"], 3)
    ps = [v.get("spearman_p") for v in result["predictors"].values() if v.get("spearman_p") is not None]
    result["interpretation"] = (
        "No predictor is statistically distinguishable from zero at p<0.05: report as a null result (small n, "
        "noisy returns, unadjusted for size/sector/surprise); do NOT read the sign as a trading signal."
        if not ps or min(ps) >= 0.05 else
        "At least one predictor is nominally significant; with few events and three predictors tested this may "
        "be chance - confirm with a larger watchlist / multiple-testing correction before drawing conclusions.")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--returns", type=Path)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--db", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)
    if not args.returns and not args.fetch:
        raise SystemExit("provide --returns <csv with ticker,date,ret_5d> or --fetch (requires yfinance)")
    with make_session_factory(get_engine(args.db))() as s:
        events = build_events(s, args.model)
    returns = load_returns(args.returns) if args.returns else fetch_returns(events, args.benchmark)
    result = correlate(events, returns)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
