"""Latency and cost per brief (project.md 7.5), read from the `briefs` table.

Reports end-to-end agent-graph latency percentiles and LLM token usage / estimated USD per brief.
Heuristic (offline) briefs cost $0 and measure only the pipeline; with ANTHROPIC_API_KEY set the same
report reflects real LLM spend. Cache hits (identical input fingerprint) cost nothing and are not in this table.
"""
from __future__ import annotations

import json
from statistics import mean, median

from sqlalchemy import select

from agents.llm import PRICE_PER_MTOK
from storage.db import get_engine, make_session_factory
from storage.models import Brief


def report(session) -> dict:
    briefs = list(session.scalars(select(Brief)))
    if not briefs:
        return {"n_briefs": 0}
    lat = sorted(b.latency_s for b in briefs)

    def pct(p):
        return lat[min(len(lat) - 1, int(p * len(lat)))]
    per_model: dict[str, dict] = {}
    for b in briefs:
        m = b.body.get("llm", "heuristic")
        pin, pout = PRICE_PER_MTOK.get(m, (0.0, 0.0))
        cost = (b.tokens_in * pin + b.tokens_out * pout) / 1e6
        d = per_model.setdefault(m, {"n": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        d["n"] += 1; d["tokens_in"] += b.tokens_in; d["tokens_out"] += b.tokens_out; d["cost_usd"] += cost
    for d in per_model.values():
        d["avg_cost_usd_per_brief"] = round(d["cost_usd"] / d["n"], 5)
        d["avg_tokens_per_brief"] = round((d["tokens_in"] + d["tokens_out"]) / d["n"], 1)
    return {"n_briefs": len(briefs), "latency_s": {"mean": round(mean(lat), 3), "median": round(median(lat), 3),
                                                   "p95": round(pct(0.95), 3), "max": round(lat[-1], 3)},
            "by_llm": per_model}


def main():
    with make_session_factory(get_engine())() as s:
        print(json.dumps(report(s), indent=2))


if __name__ == "__main__":
    main()
