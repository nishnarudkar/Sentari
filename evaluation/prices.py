"""Daily prices from Alpaca's market-data API (historical bars only - no trading endpoints) and event returns.

Needs ALPACA_API_KEY_ID / ALPACA_SECRET_KEY. Uses the SIP feed with split/dividend adjustment; Alpaca's history
starts in 2016. Bars are cached per symbol in data/cache/prices/ (gitignored).

Event timing: a call before 16:00 US/Eastern (the dataset's timestamps are taken to be Eastern) is priced from
that day's session (day 0); a call at/after 16:00 from the next trading day. Returns are measured from the
close *before* day 0, and are market-adjusted by subtracting SPY over the same days.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
CACHE = Path(__file__).resolve().parents[1] / "data" / "cache" / "prices"
HORIZONS = {"car_0_1": (0, 1), "car_0_4": (0, 4), "drift_2_11": (2, 11)}  # [first, last] trading day vs day 0


def fetch_bars(symbol: str, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """Adjusted daily closes, cached. Refetches when the cache does not cover [start, end]."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["start"] <= start.isoformat() and cached["end"] >= end.isoformat():
            return {dt.date.fromisoformat(d): c for d, c in cached["closes"].items()}
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
    params = {"symbols": symbol, "timeframe": "1Day", "start": start.isoformat(), "end": end.isoformat(),
              "adjustment": "all", "feed": "sip", "limit": 10000}
    closes: dict[str, float] = {}
    while True:
        r = requests.get(BARS_URL, headers=headers, params=params, timeout=60)
        r.raise_for_status()
        js = r.json()
        for bar in (js.get("bars") or {}).get(symbol, []):
            closes[bar["t"][:10]] = bar["c"]
        if not js.get("next_page_token"):
            break
        params["page_token"] = js["next_page_token"]
    path.write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "closes": closes}), encoding="utf-8")
    return {dt.date.fromisoformat(d): c for d, c in closes.items()}


def day0_index(days: list[dt.date], call_at: dt.datetime) -> int | None:
    """Index in the sorted trading-day list of the first session that can react to the call."""
    target = call_at.date() + dt.timedelta(days=1 if call_at.hour >= 16 else 0)
    for i, d in enumerate(days):
        if d >= target:
            return i
    return None


def event_returns(stock: dict[dt.date, float], market: dict[dt.date, float], call_at: dt.datetime) -> dict | None:
    days = sorted(set(stock) & set(market))
    i0 = day0_index(days, call_at)
    if i0 is None or i0 == 0:
        return None
    out = {}
    for name, (first, last) in HORIZONS.items():
        a, b = i0 + first - 1, i0 + last  # from the close before the window to the close of its last day
        if b >= len(days):
            return None
        r_s = stock[days[b]] / stock[days[a]] - 1
        r_m = market[days[b]] / market[days[a]] - 1
        out[name] = r_s - r_m
    out["day0"] = days[i0].isoformat()
    return out
