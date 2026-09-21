# Sentari — earnings-call & filings intelligence for retail investors

Aspect-level sentiment on earnings calls and filings (guidance, margins, demand, litigation, management tone,
liquidity), tracked quarter over quarter, with a bull / bear / skeptic / judge agent pipeline whose every claim is
traceable to the exact source sentence.

> **Research and decision-support tool. Not investment advice.** Nothing here predicts price movements.
> Final-year project, Sentiment Analysis (231CAUEC51) — Nishant Vikas Narudkar, RAIT (D Y Patil University).
> The full specification is in [project.md](project.md).

## What is built

| Area | Where | Status |
|---|---|---|
| Ingestion (transcripts, EDGAR 10-K/10-Q MD&A, news RSS, NSE), idempotent, raw-response cache | [ingestion/](ingestion) | Built. Only the offline `sample` source is exercised by tests; the network scrapers are **not verified against the live sources** |
| Transcript parsing: speaker tags, prepared-vs-Q&A sections, sentence chunking | [ingestion/normalize.py](ingestion/normalize.py) | Built + tested |
| Aspect extraction (rules + spaCy dependency parse, negation/hedge handling) | [absa_service/aspect_extraction.py](absa_service/aspect_extraction.py) | Built + tested |
| Model ladder: VADER, SentiWordNet, Loughran-McDonald, LM+directional rules, NB, Decision Tree, CNN, BiLSTM, FinBERT (zero-shot + fine-tuned) | [absa_service/models/](absa_service/models) | Built; all trained and evaluated (below) |
| MLflow tracking + `model_runs` registry driving which model serves | [absa_service/registry.py](absa_service/registry.py) | Built |
| Prepared-remarks vs Q&A delta signal | [absa_service/signals.py](absa_service/signals.py) | Built |
| Agents: extractor → bull ‖ bear → skeptic → judge (LangGraph), audit trail, input-fingerprint cache | [agents/](agents) | Built + tested; runs offline (heuristic) or with Claude |
| Storage: documents, chunks, aspect_scores, briefs, agent_traces, model_runs, drift_reports | [storage/](storage) | Built (SQLite tested; Postgres path untested) |
| Drift monitor (PSI on aspect mix + confidence shift) | [monitoring/drift.py](monitoring/drift.py) | Built + tested |
| Digest (top-3 moves) via SMTP / Slack | [delivery/digest.py](delivery/digest.py) | Rendering tested; SMTP/Slack sending **untested** |
| FastAPI service + Next.js dashboard (watchlist → trajectories → source sentence) | [absa_service/](absa_service), [dashboard/](dashboard) | Built; verified in a browser against the sample data |
| Docker, Compose, DVC, CI, Cloud Run guide | [Dockerfile](Dockerfile), [docker-compose.yml](docker-compose.yml), [dvc.yaml](dvc.yaml), [deploy/](deploy) | Written; **images not build-tested and nothing deployed** |
| Evaluation harnesses | [evaluation/](evaluation) | Built; results below |

## Quick start

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm

python -m pytest -q                              # 49 tests, fully offline
python -m absa_service.cli daily                 # ingest sample corpus -> score -> briefs -> drift -> digest
python -m absa_service.cli analyze "Gross margin expanded 180 basis points, but we are lowering our guidance."

python -m absa_service.train --transformer --transformer-zero-shot   # the full model ladder (downloads FinBERT)

uvicorn absa_service.main:app --port 8000        # API, docs at /docs
cd dashboard && npm install && npm run dev       # http://localhost:3000
```

Optional environment variables: `DATABASE_URL` (default local SQLite), `ANTHROPIC_API_KEY` (LLM-written bull/bear/judge
text instead of the offline heuristic; `SENTARI_LLM=heuristic` forces offline), `SENTARI_MODEL` (override the serving
model), `SENTARI_NLI=hf` (transformer NLI entailment in the Skeptic), `SLACK_WEBHOOK_URL`, `SMTP_*`/`DIGEST_TO`,
`SENTARI_CRON_TOKEN`, `SENTARI_USER_AGENT` (required by SEC EDGAR), `MLFLOW_TRACKING_URI`.

## Results (as measured; read the caveats)

Full tables: [results/REPORT.md](results/REPORT.md). Regenerate with the commands in [dvc.yaml](dvc.yaml).

**Model ladder** — 94 hand-written gold sentences (6 aspects × 3 classes), all models trained on the same 3,400
template-generated weak labels, single seed:

| Model | Macro-F1 | Accuracy | Accuracy on "trap" sentences |
|---|---|---|---|
| VADER | 0.647 | 0.649 | 0.38 |
| SentiWordNet | 0.490 | 0.489 | 0.27 |
| Loughran-McDonald (seed subset) | 0.756 | 0.755 | 0.42 |
| LM + directional rules | 0.892 | 0.894 | 0.85 |
| Naive Bayes (TF-IDF) | 0.743 | 0.745 | 0.69 |
| Decision Tree (TF-IDF) | 0.519 | 0.532 | 0.58 |
| CNN | 0.739 | 0.745 | 0.92 |
| BiLSTM | 0.607 | 0.638 | 0.81 |
| FinBERT, zero-shot | 0.601 | 0.606 | 0.35 |
| **FinBERT, fine-tuned** | **0.938** | **0.936** | 0.88 |

**Lexicon failure (G2).** On the 26 "trap" sentences — where finance inverts everyday polarity (falling costs and debt
are good; rising litigation expense is bad) — VADER errs on 61.5% and SentiWordNet on 73.1%, versus 57.7% for plain
Loughran-McDonald counting, 15.4% for LM + directional rules, and 11.5% for fine-tuned FinBERT.

**Grounding audit (G3), adversarial.** Faithful claims are corrupted in five ways and passed through the Skeptic:

| Corruption | Heuristic Skeptic catch rate | + NLI Skeptic (`SENTARI_NLI=hf`) |
|---|---|---|
| number swapped | 100% | 100% |
| citation removed | 100% | 100% |
| wrong chunk cited | 100% | 100% |
| fabricated claim | 100% | 100% |
| **polarity flipped** | **22.7%** | **100%** |

"Caught" = rejected or flagged `unverified`; only `supported` claims reach the brief body. The heuristic gate cannot
detect semantic contradiction, so the NLI backend should be treated as required for real use. False-rejection on faithful
claims was 0/43 in both modes.

### Limitations you should know before trusting any number above

* **The gold set is tiny (94 sentences)**; one sentence ≈ 1.1 points, so gaps of a few points are noise. One training seed.
* **Training data are weak template labels**, and the gold set shares phrasing with the templates. Trained-model
  scores (especially fine-tuned FinBERT's 0.938) are therefore optimistic and say little about performance on real,
  messier transcripts. A serious evaluation needs a few hundred hand-annotated sentences from real filings.
* **`lm_directional` was authored while looking at the gold set**, so its score is optimistic. I removed gold-driven
  words from the plain LM seed list to keep that baseline fair, but the directional rules still reflect what I read.
* **The Loughran-McDonald lexicon here is a hand-curated seed subset**, not the official ~86k-word dictionary. Drop the
  official CSV at `data/lexicons/Loughran-McDonald_MasterDictionary.csv` and re-run.
* **The sample corpus is synthetic** (fictional companies ACMX / NVLT, two quarters each). Pipeline behaviour on real
  transcripts, real EDGAR HTML, and real news is unverified.
* **The adversarial grounding audit uses synthetic corruptions and verbatim "faithful" claims**, which is the easy
  case. The human-annotated audit tooling exists (`--export` / `--score`) but **has not been run**: no human-labelled
  catch rate exists yet.
* **Signal validity (G5 / §7.4) has not been run.** It needs real forward returns (`--returns file.csv` or
  `--fetch` with yfinance); there is deliberately no bundled returns file, because any correlation computed on the
  synthetic corpus would be meaningless. Expect a null result at watchlist-sized n; the harness is built to report that honestly.
* **Latency/cost:** offline briefs take ~0.8 s and cost nothing; LLM cost per brief has not been measured because no API key was used.
* Confidence scores are a transparent heuristic, not calibrated probabilities.

## Repository layout

```
ingestion/      scrapers/, normalize.py, pipeline.py, scheduler_config.yaml
absa_service/   preprocessing/, models/, aspect_extraction.py, scoring.py, signals.py, train.py, registry.py, main.py, api.py, cli.py
agents/         extractor_agent.py, bull_bear_agents.py, skeptic_agent.py, judge_agent.py, graph.py, llm.py
storage/        models.py (SQLAlchemy), db.py, migrations/
monitoring/     drift.py
delivery/       digest.py
dashboard/      Next.js app (watchlist, ticker trajectories, brief + source drill-down, drift, model registry)
evaluation/     metrics, lexicon_failure, grounding_audit, signal_validity, latency_cost, report, model_comparison.ipynb
data/           sample/ (synthetic), gold/gold.tsv (evaluation set)
results/        snapshot of the evaluation outputs quoted above
deploy/         Cloud Run + Scheduler instructions
```

## Scope and ethics

In scope: daily batch decision support on public disclosures. Out of scope: real-time/HFT use, trade execution, any
guarantee of predictive accuracy. Respect each source's robots.txt/ToS (the NSE scraper deliberately gives up rather than
circumvent blocking); no personal data is collected.
