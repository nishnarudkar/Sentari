"""Drift monitor: week-over-week shift in aspect-mention mix and model confidence per ticker.

Proxy for "the ABSA model is degrading or the input data changed character" (project.md 5.6):
  * PSI (population stability index) between the aspect-mention distribution of the current
    window and a trailing baseline window. PSI < 0.1 stable, 0.1-0.25 moderate, > 0.25 major.
  * Standardised shift in mean prediction confidence (Cohen's d between windows).
An alert fires when PSI > PSI_ALERT or |d| > CONF_ALERT.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from absa_service.schemas import ASPECTS
from storage.models import AspectScore, DriftReport

PSI_ALERT = 0.25
CONF_ALERT = 0.8   # Cohen's d
EPS = 1e-4
MIN_OBS = 5        # need at least this many scores in each window to be meaningful


def psi(current: dict[str, float], baseline: dict[str, float]) -> float:
    total = 0.0
    for a in ASPECTS:
        c, b = max(current.get(a, 0.0), EPS), max(baseline.get(a, 0.0), EPS)
        total += (c - b) * math.log(c / b)
    return round(total, 4)


def _mix(rows: list[AspectScore]) -> dict[str, float]:
    counts = Counter(r.aspect for r in rows)
    n = sum(counts.values())
    return {a: counts.get(a, 0) / n for a in ASPECTS} if n else {}


def cohens_d(a: list[float], b: list[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    pooled = math.sqrt((pstdev(a) ** 2 + pstdev(b) ** 2) / 2)
    return round((mean(a) - mean(b)) / pooled, 4) if pooled > 1e-9 else 0.0


def compute_drift(session: Session, ticker: str | None, as_of: dt.date, window_days: int = 7,
                  baseline_days: int = 28, model_name: str | None = None) -> dict:
    cur_start = as_of - dt.timedelta(days=window_days)
    base_start = cur_start - dt.timedelta(days=baseline_days)
    q = select(AspectScore).where(AspectScore.doc_date > base_start, AspectScore.doc_date <= as_of)
    if ticker:
        q = q.where(AspectScore.ticker == ticker)
    if model_name:
        q = q.where(AspectScore.model_name == model_name)
    rows = list(session.scalars(q))
    cur = [r for r in rows if r.doc_date > cur_start]
    base = [r for r in rows if r.doc_date <= cur_start]
    if len(cur) < MIN_OBS or len(base) < MIN_OBS:
        return {"ticker": ticker or "ALL", "week_start": cur_start.isoformat(), "psi_aspect_mix": 0.0,
                "confidence_shift": 0.0, "alert": False, "status": "insufficient_data",
                "n_current": len(cur), "n_baseline": len(base)}
    p = psi(_mix(cur), _mix(base))
    d = cohens_d([r.confidence for r in cur], [r.confidence for r in base])
    alert = p > PSI_ALERT or abs(d) > CONF_ALERT
    return {"ticker": ticker or "ALL", "week_start": cur_start.isoformat(), "psi_aspect_mix": p,
            "confidence_shift": d, "alert": alert, "status": "alert" if alert else "ok",
            "n_current": len(cur), "n_baseline": len(base),
            "mix_current": _mix(cur), "mix_baseline": _mix(base)}


def run_drift(session: Session, tickers: list[str], as_of: dt.date | None = None,
              model_name: str | None = None) -> list[dict]:
    as_of = as_of or dt.date.today()
    reports = []
    for t in tickers + [None]:
        rep = compute_drift(session, t, as_of, model_name=model_name)
        session.add(DriftReport(ticker=rep["ticker"], week_start=dt.date.fromisoformat(rep["week_start"]),
                                psi_aspect_mix=rep["psi_aspect_mix"], confidence_shift=rep["confidence_shift"],
                                alert=rep["alert"], detail={k: v for k, v in rep.items()
                                                            if k not in ("ticker", "week_start")}))
        reports.append(rep)
    session.commit()
    return reports
