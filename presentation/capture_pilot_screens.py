"""Capture dashboard screenshots of the REAL 10-company pilot for the presentation (Playwright + installed Edge).

Needs the API (DATABASE_URL -> pilot DB) on :8000 and the dashboard on :3000.
    python presentation/capture_pilot_screens.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "assets"
DASH, API = "http://localhost:3000", "http://localhost:8000"
HIDE_DEV_BADGE = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                  "s.textContent='nextjs-portal{display:none!important}';document.head.appendChild(s)})")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    brief_id = json.load(urllib.request.urlopen(f"{API}/tickers/BA/briefs", timeout=60))[0]["id"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1360, "height": 860}, device_scale_factor=1.5)
        ctx.add_init_script(HIDE_DEV_BADGE)
        page = ctx.new_page()
        page.goto(DASH, wait_until="networkidle"); page.get_by_text("Tickers").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1200); page.screenshot(path=str(OUT / "pilot_watchlist.png"))
        page.goto(f"{DASH}/ticker/BA", wait_until="networkidle"); page.get_by_text("Aspect trajectories").wait_for(timeout=60_000)
        page.wait_for_timeout(1800); page.screenshot(path=str(OUT / "pilot_ba_trajectories.png"))
        page.goto(f"{DASH}/briefs/{brief_id}", wait_until="networkidle"); page.get_by_text("Summary").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1200); page.screenshot(path=str(OUT / "pilot_ba_brief.png"))
        page.get_by_role("button", name="src").first.click(); page.get_by_text("Model verdicts").wait_for(timeout=30_000)
        page.wait_for_timeout(800); page.screenshot(path=str(OUT / "pilot_ba_source.png"))
        browser.close()
    print("saved", sorted(p.name for p in OUT.glob("pilot_*.png")))


if __name__ == "__main__":
    main()
