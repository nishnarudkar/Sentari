"""Capture dashboard screenshots of the REAL 10-company pilot for the presentation (Playwright + installed Edge).

Needs the API (DATABASE_URL -> pilot DB) on :8000 and the dashboard on :3000.
    python presentation/capture_pilot_screens.py
Writes full screenshots plus content crops (no browser chrome / side margins) to presentation/assets/.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "assets"
DASH, API = "http://localhost:3000", "http://localhost:8000"
HIDE_DEV_BADGE = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                  "s.textContent='nextjs-portal{display:none!important}';document.head.appendChild(s)})")
SCALE = 1.5  # device scale factor; crops below are in CSS pixels


def crop(name: str, box_css: tuple[int, int, int, int]) -> None:
    im = Image.open(OUT / f"{name}.png")
    x0, y0, x1, y1 = (int(v * SCALE) for v in box_css)
    im.crop((x0, y0, min(x1, im.width), min(y1, im.height))).save(OUT / f"{name}_crop.png")


def scroll_to(page, text: str, offset: int = 16) -> None:
    page.evaluate("""([t, off]) => { const el = [...document.querySelectorAll('h1,h2,h3,summary')].find(e => e.textContent.includes(t));
        window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - off); }""", [text, offset])
    page.wait_for_timeout(500)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    brief_id = json.load(urllib.request.urlopen(f"{API}/tickers/BA/briefs", timeout=60))[0]["id"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1360, "height": 860}, device_scale_factor=SCALE)
        ctx.add_init_script(HIDE_DEV_BADGE)
        page = ctx.new_page()

        # watchlist: 10 real companies + top moves
        page.goto(DASH, wait_until="networkidle"); page.get_by_text("Tickers").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1200); page.screenshot(path=str(OUT / "pilot_watchlist.png"))
        page.screenshot(path=str(OUT / "pilot_watchlist_full.png"), full_page=True)

        # ticker trajectories + drill-down + source drawer
        page.goto(f"{DASH}/ticker/BA", wait_until="networkidle"); page.get_by_text("Aspect trajectories").wait_for(timeout=60_000)
        page.wait_for_timeout(1800); page.screenshot(path=str(OUT / "pilot_ba_trajectories.png"))
        card = page.locator(".card", has_text="Liquidity").first
        card.locator("circle").nth(-2).click()        # the Jan-2025 call (cash burn after the strike)
        page.get_by_text("Section").first.wait_for(timeout=30_000)
        scroll_to(page, "Liquidity ·")
        page.screenshot(path=str(OUT / "pilot_ba_drilldown.png"))
        page.locator("table tbody tr").first.click(); page.get_by_text("Model verdicts").wait_for(timeout=30_000)
        page.wait_for_timeout(800); page.screenshot(path=str(OUT / "pilot_ba_source.png"))

        # brief: summary, bull/bear, audit trail (skeptic step)
        page.goto(f"{DASH}/briefs/{brief_id}", wait_until="networkidle"); page.get_by_text("Summary").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1200); page.screenshot(path=str(OUT / "pilot_ba_brief.png"))
        page.get_by_role("button", name="Show agent audit trail").click(); page.wait_for_timeout(400)
        page.locator("details").nth(3).locator("summary").click(); page.wait_for_timeout(400)
        scroll_to(page, "4. skeptic")
        page.screenshot(path=str(OUT / "pilot_ba_audit.png"))

        # drift monitor, model registry, API docs
        page.goto(f"{DASH}/drift", wait_until="networkidle"); page.get_by_text("Drift monitor").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1000); page.screenshot(path=str(OUT / "pilot_drift.png"))
        page.goto(f"{DASH}/models", wait_until="networkidle"); page.get_by_text("Model registry").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1000); page.screenshot(path=str(OUT / "pilot_models.png"))
        page.goto(f"{API}/docs", wait_until="networkidle"); page.get_by_text("/analyze").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1200); page.screenshot(path=str(OUT / "pilot_api_docs.png"))
        browser.close()

    # content crops (CSS px): drop the nav bar and the empty side margins
    for name in ("pilot_watchlist", "pilot_ba_trajectories", "pilot_ba_brief", "pilot_ba_drilldown", "pilot_drift",
                 "pilot_models"):
        crop(name, (137, 50, 1223, 640))
    crop("pilot_ba_source", (137, 0, 1360, 700))
    crop("pilot_ba_audit", (137, 0, 1223, 640))
    crop("pilot_api_docs", (0, 0, 1360, 640))
    print("saved", sorted(p.name for p in OUT.glob("pilot_*.png")))


if __name__ == "__main__":
    main()
