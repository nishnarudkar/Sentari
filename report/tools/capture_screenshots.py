"""Capture report screenshots with Playwright driving the locally installed Microsoft Edge.

Prerequisites (all running locally):
    API        uvicorn absa_service.main:app --port 8000   (with a DB where `cli daily` has run)
    dashboard  cd dashboard && npm run dev                  (port 3000)
    MLflow     mlflow ui --backend-store-uri ./mlruns --port 5000   (optional)

    pip install playwright
    python report/tools/capture_screenshots.py
"""
from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
DASH, API, MLFLOW = "http://localhost:3000", "http://localhost:8000", "http://localhost:5000"
VIEW = {"width": 1360, "height": 860}


def settle(page, text: str | None = None, ms: int = 900):
    page.wait_for_load_state("networkidle")
    if text:
        page.get_by_text(text).first.wait_for(timeout=30_000)
    page.wait_for_timeout(ms)


def shot(page, name: str, full: bool = False, clip: dict | None = None):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full, clip=clip)
    print("saved", name)


def terminal_html(title: str, cmd: str, output: str) -> str:
    body = html.escape(output.rstrip())
    return f"""<html><body style="margin:0;background:#1e1e1e">
<div style="font:13px/1.45 Consolas,'Cascadia Mono',monospace;color:#d4d4d4;padding:0;width:1100px">
<div style="background:#2d2d2d;color:#9d9d9d;padding:8px 14px;font:12px Segoe UI">{html.escape(title)}</div>
<pre style="margin:0;padding:14px 16px;white-space:pre-wrap"><span style="color:#6a9955">PS Sentari&gt;</span> <span style="color:#dcdcaa">{html.escape(cmd)}</span>
{body}</pre></div></body></html>"""


def run(cmd: list[str], env_extra: dict | None = None) -> str:
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "SENTARI_LLM": "heuristic", **(env_extra or {})}
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    return p.stdout + ("" if p.returncode == 0 else p.stderr[-2000:])


def lexicon_table() -> str:
    """Same table `python -m evaluation.lexicon_failure` prints, from the committed results snapshot."""
    import json
    sys.path.insert(0, str(ROOT))
    from evaluation.lexicon_failure import markdown_table
    return markdown_table(json.loads((ROOT / "results" / "lexicon_failures.json").read_text(encoding="utf-8")))


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        _new_context = browser.new_context

        def new_context(**kw):
            c = _new_context(**kw)
            # hide the Next.js dev-mode indicator badge; it is not part of the app
            c.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                              "s.textContent='nextjs-portal{display:none!important}';document.head.appendChild(s)})")
            return c
        browser.new_context = new_context
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=1.5, color_scheme="light")
        page = ctx.new_page()

        # 1 watchlist
        page.goto(DASH); settle(page, "Top aspect moves")
        shot(page, "01_watchlist", full=True)

        # 2 ticker trajectories
        page.goto(f"{DASH}/ticker/ACMX"); settle(page, "Aspect trajectories", 1500)
        shot(page, "02_ticker_trajectories")

        # 3 drill-down: click the latest point of the Management tone chart
        card = page.locator(".card", has_text="Management tone").first
        card.locator("circle").last.click()
        settle(page, "Section", 1200)
        page.locator("h2", has_text="Management tone").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shot(page, "03_drilldown_sentences")

        # 4 source drawer from the drill-down table
        page.locator("table tbody tr").first.click()
        settle(page, "Model verdicts", 1000)
        shot(page, "04_source_drawer")

        # 5-6 brief
        page.goto(f"{DASH}/briefs/1"); settle(page, "Summary", 1200)
        shot(page, "05_brief_top")
        page.evaluate("() => { const h = [...document.querySelectorAll('h2')].find(e => e.textContent.startsWith('Bull vs bear'));"
                      " window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 24); }")
        page.wait_for_timeout(400)
        shot(page, "06_brief_bull_bear")
        page.get_by_role("button", name="src").first.click(); settle(page, "Model verdicts", 900)
        shot(page, "07_brief_citation_drawer")
        page.get_by_role("button", name="Close").click(); page.wait_for_timeout(300)
        page.get_by_role("button", name="Show agent audit trail").click(); page.wait_for_timeout(400)
        page.locator("details").nth(3).locator("summary").click()      # skeptic step
        page.locator("details").nth(3).scroll_into_view_if_needed(); page.wait_for_timeout(500)
        shot(page, "08_brief_audit_trail")

        # 9 drift, 10 models
        page.goto(f"{DASH}/drift"); settle(page, "Drift monitor", 900)
        shot(page, "09_drift_monitor", full=True)
        page.goto(f"{DASH}/models"); settle(page, "Model registry", 900)
        shot(page, "10_model_registry", full=True)

        # 11 dark mode + 12 phone width
        dark = browser.new_context(viewport=VIEW, device_scale_factor=1.5, color_scheme="dark").new_page()
        dark.goto(f"{DASH}/ticker/NVLT"); settle(dark, "Aspect trajectories", 1500)
        shot(dark, "11_dark_mode_ticker")
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                    is_mobile=True).new_page()
        phone.goto(DASH); settle(phone, "Tickers", 900)
        shot(phone, "12_mobile_watchlist")

        # 13 API docs, 14 live /analyze call through Swagger's JSON view
        page.goto(f"{API}/docs"); settle(page, "Sentari", 1500)
        shot(page, "13_api_swagger")

        # 15 MLflow
        try:
            # the MLflow UI polls continuously, so never wait for network idle here
            import json
            import urllib.request
            req = urllib.request.Request(f"{MLFLOW}/api/2.0/mlflow/experiments/get-by-name?experiment_name=sentari-absa-ladder")
            exp_id = json.load(urllib.request.urlopen(req, timeout=20))["experiment"]["experiment_id"]
            page.goto(f"{MLFLOW}/#/experiments/{exp_id}/runs", wait_until="domcontentloaded", timeout=30_000)
            page.get_by_text("finbert_zeroshot").first.wait_for(timeout=60_000)
            page.wait_for_timeout(2500)
            shot(page, "14_mlflow_runs")
        except Exception as exc:  # noqa: BLE001
            print("mlflow skipped:", exc)

        # terminal captures (real command output rendered as a terminal window)
        term = ctx.new_page()
        for name, title, cmd, out in [
            ("15_terminal_tests", "pytest", "python -m pytest -q",
             run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings"])),
            ("16_terminal_analyze", "sentari analyze", 'python -m absa_service.cli analyze "<earnings text>"',
             run([sys.executable, "-m", "absa_service.cli", "analyze",
                  "Gross margin expanded 180 basis points on favorable mix. Demand held up in automation, but "
                  "aerospace orders declined. We are lowering our full-year guidance. We repaid 200 million dollars "
                  "of debt and our leverage ratio improved. We are unable to quantify the litigation exposure.",
                  "--model", "lm_directional"])),
            ("17_terminal_lexicon_failure", "lexicon failure analysis", "python -m evaluation.lexicon_failure",
             lexicon_table()),
        ]:
            if not out:
                continue
            term.set_content(terminal_html(title, cmd, out))
            box = term.locator("body > div").bounding_box()
            shot(term, name, clip={"x": 0, "y": 0, "width": box["width"], "height": box["height"]})
        browser.close()


if __name__ == "__main__":
    main()
