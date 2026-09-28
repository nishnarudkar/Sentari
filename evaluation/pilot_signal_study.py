"""Preliminary signal-validity study on the real-call pilot (project.md 7.4).

Question: does the prepared-remarks-vs-Q&A sentiment gap ("delta") of an earnings call relate to the stock's
subsequent market-adjusted return, beyond plain document-level sentiment?

    python -m evaluation.pilot_signal_study          # -> results/pilot/signal_validity_preliminary.json

PRELIMINARY: the sentiment scores come from two models that disagree on 35% of real sentences, and neither has
been validated on real text yet (see evaluation/real_gold.py). Results are therefore reported for both models
side by side, and must be re-run once the human-labelled gold set decides which model to trust.

Design:
  * events: pilot transcripts with both sections scored, from 2016 (Alpaca's price history starts then)
  * returns: market-adjusted (minus SPY) over [0,+1] (reaction), [0,+4] (week), [+2,+11] (post-call drift)
  * tests: Spearman rho with bootstrap CI; OLS  CAR ~ delta + doc_level [+ forward-EPS revision] + ticker fixed
    effects, HC1 robust errors. 2 models x 3 horizons -> Bonferroni-adjusted p-values reported for delta.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb

from evaluation.prices import HORIZONS, event_returns, fetch_bars
from evaluation.signal_validity import build_events, correlate

ROOT = Path(__file__).resolve().parents[1]
SUBSET = ROOT / "data" / "transcripts" / "hf_subset.parquet"
EPS_DIR = ROOT / "data" / "raw" / "glopardo_sp500_earnings_transcripts"
OUT = ROOT / "results" / "pilot" / "signal_validity_preliminary.json"
MODELS = ("lm_directional", "finbert_ft")
START = dt.date(2016, 1, 1)


def call_times() -> dict[tuple[str, dt.date], dt.datetime]:
    rows = duckdb.connect().execute(f"SELECT symbol, date FROM '{SUBSET.as_posix()}'").fetchall()
    return {(s, dt.date.fromisoformat(d[:10])): dt.datetime.fromisoformat(d) for s, d in rows}


def eps_revisions() -> dict[tuple[str, dt.date], float]:
    """Quarter-on-quarter change in 12-month forward EPS at the call (glopardo dataset), if available locally."""
    if not EPS_DIR.exists():
        return {}
    rows = duckdb.connect().execute(f"""
        SELECT ticker, earnings_date, eps12mfwd_eoq,
               lag(eps12mfwd_eoq) OVER (PARTITION BY ticker ORDER BY earnings_date) AS prev
        FROM '{(EPS_DIR / '*.parquet').as_posix()}' WHERE earnings_date IS NOT NULL""").fetchall()
    out = {}
    for t, d, cur, prev in rows:
        if cur is not None and prev not in (None, 0):
            out[(t, dt.date.fromisoformat(d[:10]))] = (cur - prev) / abs(prev)
    return out


def ols(rows: list[dict], y: str, with_eps: bool) -> dict:
    import numpy as np
    import statsmodels.api as sm

    rows = [r for r in rows if r["delta"] is not None and r["doc_level"] is not None and (not with_eps or r.get("eps_rev") is not None)]
    tickers = sorted({r["ticker"] for r in rows})
    X = [[r["delta"], r["doc_level"]] + ([r["eps_rev"]] if with_eps else []) +
         [1.0 if r["ticker"] == t else 0.0 for t in tickers[1:]] for r in rows]
    X = sm.add_constant(np.asarray(X, dtype=float))
    fit = sm.OLS(np.asarray([r[y] for r in rows]), X).fit(cov_type="HC1")
    names = ["const", "delta", "doc_level"] + (["eps_rev"] if with_eps else [])
    return {"n": len(rows), "r2": round(float(fit.rsquared), 4),
            **{f"{k}_coef": round(float(fit.params[i]), 5) for i, k in enumerate(names) if k != "const"},
            **{f"{k}_p": round(float(fit.pvalues[i]), 4) for i, k in enumerate(names) if k != "const"}}


def run(session) -> dict:
    times, eps = call_times(), eps_revisions()
    tickers = sorted({t for t, _ in times})
    end = max(times.values()).date() + dt.timedelta(days=30)
    market = fetch_bars("SPY", START - dt.timedelta(days=10), end)
    prices = {t: fetch_bars(t, START - dt.timedelta(days=10), end) for t in tickers}

    n_tests = len(MODELS) * len(HORIZONS)
    result: dict = {"status": "PRELIMINARY - models not yet validated on real sentences", "models": {},
                    "n_tests_for_bonferroni": n_tests, "eps_control_available": bool(eps)}
    for model in MODELS:
        rows = []
        for e in build_events(session, model):
            key = (e["ticker"], e["date"])
            if e["date"] < START or key not in times:
                continue
            ret = event_returns(prices[e["ticker"]], market, times[key])
            if ret:
                rows.append({**e, **ret, "eps_rev": eps.get(key)})
        per_h = {}
        for h in HORIZONS:
            corr = correlate(rows, {(r["ticker"], r["date"]): r[h] for r in rows})
            fit = ols(rows, h, with_eps=False)
            fit_eps = ols(rows, h, with_eps=True) if eps else None
            per_h[h] = {"spearman": corr["predictors"], "ols": fit, "ols_with_eps_control": fit_eps,
                        "delta_p_bonferroni": round(min(1.0, fit["delta_p"] * n_tests), 4)}
        result["models"][model] = {"n_events": len(rows), "horizons": per_h,
                                   "first_event": str(min(r["date"] for r in rows)), "last_event": str(max(r["date"] for r in rows))}
    any_sig = any(h["delta_p_bonferroni"] < 0.05 for m in result["models"].values() for h in m["horizons"].values())
    result["interpretation"] = (
        "At least one delta coefficient survives Bonferroni correction; check it holds for BOTH models before "
        "reading anything into it, and re-run after the real gold set picks the model."
        if any_sig else
        "No delta coefficient survives Bonferroni correction for 6 tests: no evidence (yet) that the prepared-vs-Q&A "
        "gap predicts market-adjusted returns in this pilot. Report as a null result pending model validation.")
    return result


def main():
    import sentari_env  # noqa: F401  (Alpaca keys, DATABASE_URL)
    from storage.db import get_engine, make_session_factory
    with make_session_factory(get_engine())() as s:
        res = run(s)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for model, m in res["models"].items():
        print(f"\n{model}: {m['n_events']} events ({m['first_event']} .. {m['last_event']})")
        for h, v in m["horizons"].items():
            sp = v["spearman"]
            o = v["ols"]
            e = v["ols_with_eps_control"] or {}
            print(f"  {h:11s} rho(delta)={sp['delta'].get('spearman_rho')} p={sp['delta'].get('spearman_p')} | "
                  f"rho(doc)={sp['doc_level'].get('spearman_rho')} | OLS delta={o['delta_coef']} p={o['delta_p']} "
                  f"(Bonf {v['delta_p_bonferroni']}) | +EPS: delta p={e.get('delta_p')} n={e.get('n')}")
    print("\n" + res["interpretation"])


if __name__ == "__main__":
    main()
