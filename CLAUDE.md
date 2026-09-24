# CLAUDE.md — Sentari

Final-year project: an earnings-call & filings intelligence platform (aspect-level sentiment + grounded bull/bear/skeptic/judge briefs). The spec is [project.md](project.md); measured results and limitations are in [README.md](README.md) and `results/`. **Research/decision-support only — never present output as investment advice.**

Remote: `https://github.com/nishnarudkar/Sentari.git` (branch `main`). The user has authorised pushing all work there; commit in small logical steps.

## Commands

```bash
python -m pytest -q                                   # 58 tests, fully offline (~30 s)
python -m absa_service.cli daily                      # ingest sample -> score -> briefs -> drift -> digest
python -m absa_service.cli analyze "text"             # aspect sentiment for free text
python -m absa_service.train [--transformer] [--transformer-zero-shot]   # model ladder -> artifacts/, MLflow, model_runs
python -m evaluation.lexicon_failure                  # lexicon failure analysis
python -m evaluation.grounding_audit --adversarial    # add SENTARI_NLI=hf for the NLI skeptic
python -m evaluation.report                           # artifacts/results/REPORT.md
uvicorn absa_service.main:app --port 8000             # API (docs at /docs)
cd dashboard && npm run dev                           # http://localhost:3000  (npm run lint = tsc, npm run build)
```

Config: `.env` (copy of `.env.example`, gitignored) is loaded by `sentari_env.py`, which every package `__init__` imports so it runs before import-time env reads; real env vars win, empty values are ignored, `SENTARI_SKIP_DOTENV=1` disables it (tests set this). New env vars must be added to `.env.example` (a test enforces it). What the user must supply and how: `SETUP.md`.

Env vars: `DATABASE_URL` (default `sqlite:///sentari.db`), `SENTARI_MODEL`, `SENTARI_LLM=heuristic` (force offline agents), `ANTHROPIC_API_KEY`, `SENTARI_NLI=hf`, `SENTARI_CRON_TOKEN`, `SENTARI_USER_AGENT` (EDGAR), `MLFLOW_TRACKING_URI`, `SLACK_WEBHOOK_URL`, `SMTP_*`/`DIGEST_TO`. `tests/conftest.py` pins `SENTARI_LLM=heuristic` and `SENTARI_MODEL=lm_directional`; keep tests independent of local artifacts/DB.

## Architecture (data flow)

`ingestion/` (scrapers → `normalize.py` chunking → `pipeline.py`, idempotent by content hash) → `storage/` (SQLAlchemy: documents, chunks, aspect_scores, briefs, agent_traces, model_runs, drift_reports) → `absa_service/` (`aspect_extraction.py` → model → `scoring.py` writes `aspect_scores` + embeddings; `signals.py` has the prepared-vs-Q&A delta) → `agents/` (`graph.py`: extractor → bull ‖ bear → skeptic → judge; briefs cached by input fingerprint) → `absa_service/api.py` + `dashboard/`. `monitoring/drift.py` (PSI + confidence shift), `delivery/digest.py`, `absa_service/orchestration.py` (`run_daily`, exposed as `POST /run/daily`).

Key conventions:
- Every model implements `SentimentModel.predict(list[Item]) -> list[Prediction]` (`absa_service/models/base.py`); labels are `negative|neutral|positive`, score is signed in [-1, 1].
- `serving.get_model(None)` resolves: explicit name > `SENTARI_MODEL` > registry `serving` flag > `lm_directional`. Trained weights live in `artifacts/models/` (gitignored); missing weights fall back to the rule-based model.
- Bull/bear claim ids use distinct prefixes (`bl`/`br`) — they key the brief and audit trail.
- Only claims the skeptic marks `supported` reach a brief's sections; `unverified` are listed separately; `rejected` are dropped but kept in `agent_traces`.
- The skeptic's heuristic polarity check is weak (22.7% on flipped claims); `SENTARI_NLI=hf` fixes this. Near-verbatim quotes are exempt from the polarity-cue rejection.

## Rules for working here

- **No test-set leakage.** `data/gold/gold.tsv` is evaluation-only. Never add gold-derived words/rules to lexicons or templates, and never train on it (`train.py` filters gold sentences out of the weak labels). `lm_directional` was already written with sight of the gold set — its score is optimistic; say so when reporting.
- **Report results honestly**, including null/negative ones (project.md G5). Update `README.md` limitations if behaviour changes. Don't claim things that haven't been run.
- **Unverified so far** (do not assert they work): live EDGAR/NSE/news scrapers, Docker image builds, Cloud Run deploy, SMTP/Slack sending, signal-validity run (needs real returns; there is intentionally no bundled returns file), human grounding audit, LLM cost per brief.
- Sample data in `data/sample/` is **synthetic** (fictional ACMX/NVLT). Don't present it as real.
- Respect source ToS/robots.txt; don't add scrapers that circumvent blocking. EDGAR needs a contact User-Agent supplied by the user — don't invent one.
- Loughran-McDonald in `absa_service/models/lm_lexicon_data.py` is a hand-curated seed subset; the official CSV can be dropped in at `data/lexicons/Loughran-McDonald_MasterDictionary.csv`.

## Environment gotchas (Windows)

- Use the Write/Edit tools for creating files; large heredocs with backticks/quotes broke in the Bash tool.
- Don't `taskkill /IM node.exe` (kills unrelated processes); stop servers by PID/command line.
- Git converts line endings (`.gitattributes` forces LF); CRLF warnings are harmless.
- `dashboard/` is Next 16 / React 19 (0 npm audit vulnerabilities at last check). Next may auto-generate `AGENTS.md`/`CLAUDE.md` in `dashboard/` on `npm run dev` — delete them, don't commit.
- `report/`: project report (docx + pdf). Regenerate: `python report/tools/make_figures.py`; `python report/tools/capture_screenshots.py` (needs API on :8000, dashboard on :3000, optional `mlflow ui` on :5000; drives installed Edge via Playwright); `cd report/tools && npm install && node build_report.js`; `export_pdf.ps1` (Word COM: refreshes TOCs, exports PDF). Numbers in `build_report.js` prose are hand-checked against `results/` — re-verify if results change.
- Generated/ignored: `artifacts/`, `mlruns/`, `*.db`, `data/cache/`, `node_modules/`, `.next/`. `results/` is the committed snapshot of evaluation output.
