# Sentari
### An Earnings-Call & Filings Intelligence Platform for Retail Investors

**Final Year Project — Sentiment Analysis (231CAUEC51)**
**Author:** Nishant Vikas Narudkar
**Institution:** Ramrao Adik Institute of Technology (D Y Patil University)

---

## 1. Problem Statement

Retail investors following a watchlist of 15–20 stocks cannot realistically read every earnings call transcript, 10-K/10-Q filing, and news wire that touches those companies each quarter. Signal that matters — a subtle softening in guidance language, a spike in hedging during Q&A, litigation risk buried in a footnote — is routinely missed, while institutional desks pay for exactly this kind of monitoring.

**Sentari** is a daily intelligence service that watches a user's watchlist, extracts sentiment at the level of specific financial aspects (not just "positive/negative"), tracks how that sentiment moves quarter over quarter, and produces a grounded, debated, human-readable brief — with every claim traceable back to the exact sentence that generated it.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Aspect-level (not document-level) sentiment extraction from unstructured financial text |
| G2 | Demonstrate, empirically, where general-purpose lexicons fail on financial language |
| G3 | Multi-agent reasoning (bull/bear/skeptic/judge) that is **grounded** — no hallucinated claims |
| G4 | A real deployed service: scheduled ingestion, persistent storage, drift monitoring, a UI |
| G5 | An honest evaluation — including where the signal does *not* predict anything |

---

## 3. Scope

### In scope
- US and NSE/BSE-listed companies with public earnings call transcripts and filings
- Aspect set: **guidance, margins, demand, litigation, management tone, liquidity**
- Daily batch pipeline (not real-time tick-level)
- Web dashboard + email/Slack digest

### Out of scope (explicitly — state this in the report)
- Real-time intraday sentiment / HFT-adjacent use cases
- Trade execution or portfolio management
- Guaranteeing predictive accuracy of any signal — this is a research/decision-support tool, not investment advice

---

## 4. System Architecture

```
                        ┌─────────────────────┐
                        │   Scheduler (Cloud   │
                        │   Scheduler / Cron)  │
                        └──────────┬───────────┘
                                   │ triggers daily
                                   ▼
┌──────────────────────────────────────────────────────────┐
│                     INGESTION SERVICE                      │
│  - Transcript scraper (earnings call APIs / IR pages)      │
│  - Filing fetcher (10-K/10-Q MD&A sections, NSE filings)    │
│  - News wire fetcher                                        │
│  - Dedup + normalize + chunk                                │
└──────────────────────┬───────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│                   ABSA SERVICE (FastAPI)                    │
│  - POS tagging + dependency parsing (spaCy)                 │
│  - Aspect extraction (rule + model hybrid)                  │
│  - Sentiment scoring per aspect:                             │
│      Lexicon baseline (VADER / SentiWordNet / Loughran-McDonald) │
│      ML baseline (Naive Bayes / Decision Tree, TF-IDF)       │
│      DL model (CNN / LSTM)                                   │
│      Transformer (fine-tuned FinBERT-class model, PyTorch)   │
│  - All model versions tracked in MLflow                      │
└──────────────────────┬───────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                             │
│  - Postgres: aspect-sentiment time series, briefs, audit log │
│  - pgvector / Qdrant: chunk embeddings for grounding retrieval│
└──────────────────────┬───────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│                 AGENT ORCHESTRATION (LangGraph)              │
│                                                               │
│   Extractor Agent → pulls relevant chunks + aspect scores     │
│           │                                                   │
│           ▼                                                   │
│   Bull Agent  ──┐                                             │
│   Bear Agent  ──┼──► Skeptic Agent (checks every claim         │
│                 │      against retrieved source spans —        │
│                 │      rejects/flags ungrounded claims)         │
│                 ▼                                              │
│           Judge Agent → final brief + confidence score          │
└──────────────────────┬───────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│                     DELIVERY LAYER                           │
│  - Next.js dashboard (drill-down: brief → source sentence)   │
│  - Daily email / Slack digest                                 │
│  - Drift monitor dashboard (aspect-mix shift week over week)  │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Component Breakdown

### 5.1 Ingestion Service
- Sources: earnings call transcript providers, company IR pages, SEC EDGAR (10-K/10-Q), NSE/BSE filings, news wire.
- Responsibilities: fetch → dedupe → normalize encoding → sentence/paragraph chunking → tag with `(ticker, doc_type, date, section)`.
- Runs on a schedule; failures logged and retried; idempotent (safe to re-run without duplicating data).

### 5.2 ABSA Service
- **Preprocessing:** sentence segmentation tuned for transcript formatting (speaker tags, cross-talk), negation scope detection, hedge-word normalization ("may," "expect," "believe").
- **Aspect extraction:** noun-phrase candidates via POS tagging, refined with dependency parsing to find the opinion word governing each aspect; hybrid with a small supervised aspect tagger where rules are insufficient.
- **Polarity scoring — build and compare all of these, not just the best one:**
  1. Lexicon-based: VADER, SentiWordNet, Loughran-McDonald financial lexicon
  2. Classical ML: Naive Bayes, Decision Tree on TF-IDF
  3. Deep learning: CNN, LSTM with pre-trained embeddings
  4. Transformer: fine-tuned FinBERT-class model
- **Prepared-remarks vs. Q&A delta:** compute aspect sentiment separately for scripted opening remarks and unscripted Q&A; the gap is the platform's signature signal.

### 5.3 Agent Layer
- **Extractor Agent:** given a ticker and date range, pulls the top-k relevant chunks per aspect from the vector store.
- **Bull / Bear Agents:** construct the strongest case from the extracted, scored aspects — explicitly instructed to cite the source chunk for every claim.
- **Skeptic Agent:** the grounding gate. For every claim in the bull/bear output, checks whether the cited chunk actually supports it (embedding similarity + entailment check). Claims that fail are stripped or flagged `unverified`.
- **Judge Agent:** synthesizes a final brief with a confidence score, weighted by how much of the bull/bear case survived the skeptic's check.

### 5.4 Storage
- Postgres tables: `documents`, `aspect_scores`, `briefs`, `agent_traces` (full audit trail — every sentence in a brief traceable to source), `model_runs`.
- Vector store for retrieval-augmented grounding.

### 5.5 Delivery
- Dashboard: watchlist view → per-ticker aspect trajectory charts → click into any data point to see the source sentence and which model scored it.
- Digest: top 3 aspect-sentiment moves across the watchlist, daily.

### 5.6 Monitoring
- **Drift monitor:** track the distribution of aspect mentions and confidence scores week over week per ticker; alert on unexpected shifts (a proxy for the ABSA model degrading or the input data changing character).
- **Model registry:** every model version, its evaluation metrics, and which one is currently serving — tracked in MLflow.

---

## 6. Technology Stack

| Layer | Technology |
|---|---|
| Language | Python (services), TypeScript (dashboard) |
| NLP | spaCy (POS/dependency), NLTK/VADER, SentiWordNet |
| ML/DL | scikit-learn, PyTorch |
| Agent orchestration | LangGraph, LangChain |
| API | FastAPI |
| Experiment tracking | MLflow |
| Data versioning | DVC |
| Database | PostgreSQL |
| Vector store | pgvector or Qdrant |
| Scheduling | Cloud Scheduler / Airflow |
| Containerization | Docker, Docker Compose |
| Deployment | Google Cloud Run |
| Frontend | Next.js |
| Notifications | SMTP / Slack API |

---

## 7. Evaluation Plan

This is the section that separates the project from a demo. Report all of the following honestly, including negative results.

1. **Model ladder comparison** — one table, one held-out test set, every approach (lexicon → ML → DL → transformer) scored on the same aspect-level sentiment task. Precision/recall/F1 per class, not just accuracy.
2. **Lexicon failure analysis** — a curated set of financial sentences where VADER/SentiWordNet mis-score due to domain-specific vocabulary; quantify the error rate against the financial lexicon and the fine-tuned model.
3. **Grounding audit** — sample N generated briefs, manually verify what fraction of claims are actually supported by the cited source; report the skeptic agent's catch rate.
4. **Signal validity check** — does the prepared-remarks-vs-Q&A sentiment delta correlate with subsequent price movement (e.g., 5-day post-earnings drift) better than raw document-level sentiment? Report the correlation honestly even if it is weak or absent — a clearly reasoned null result is a legitimate and defensible finding.
5. **Latency and cost** — end-to-end time and LLM token cost per brief generated, since this is a deployed service, not a one-off script.

---

## 8. Syllabus Mapping (231CAUEC51 — Sentiment Analysis)

| Module | Where it appears in Sentari |
|---|---|
| M1: Levels, challenges, applications | Aspect-level vs. document-level framing; ethics section on non-advice framing |
| M2: Preprocessing & feature engineering | Transcript-specific sentence segmentation, negation/hedge handling, TF-IDF, embeddings |
| M3: Lexicon & knowledge-based | VADER/SentiWordNet vs. Loughran-McDonald comparison; documented lexicon failure analysis |
| M4: ML & DL approaches | Naive Bayes, Decision Tree, CNN, LSTM, transformer fine-tune — full ladder |
| M5: Aspect-based sentiment analysis | Core of the project — aspect extraction via POS/dependency parsing, opinion-target extraction, domain adaptation |
| M6: Applications | Market research / financial analytics application, deployed and evaluated |

---

## 9. Repository Structure

```
sentari/
├── ingestion/
│   ├── scrapers/
│   ├── normalize.py
│   └── scheduler_config.yaml
├── absa_service/
│   ├── preprocessing/
│   ├── models/
│   │   ├── lexicon.py
│   │   ├── classical_ml.py
│   │   ├── deep_learning.py
│   │   └── transformer.py
│   ├── aspect_extraction.py
│   └── main.py               # FastAPI app
├── agents/
│   ├── extractor_agent.py
│   ├── bull_bear_agents.py
│   ├── skeptic_agent.py
│   ├── judge_agent.py
│   └── graph.py               # LangGraph orchestration
├── storage/
│   ├── models.py               # SQLAlchemy schema
│   └── migrations/
├── monitoring/
│   └── drift.py
├── dashboard/                  # Next.js app
├── evaluation/
│   ├── model_comparison.ipynb
│   ├── grounding_audit.py
│   └── signal_validity.py
├── docker-compose.yml
├── mlflow/
├── dvc.yaml
└── README.md
```

---

## 10. Roadmap

| Phase | Weeks | Deliverable |
|---|---|---|
| 1. Data pipeline | 1–2 | Ingestion service pulling transcripts + filings for a 10-ticker pilot watchlist |
| 2. Preprocessing & lexicon baseline | 3 | Cleaned corpus; VADER/SentiWordNet/Loughran-McDonald scored; failure analysis draft |
| 3. Classical ML + DL models | 4–5 | Naive Bayes, Decision Tree, CNN, LSTM trained and logged in MLflow |
| 4. Aspect extraction | 6–7 | POS/dependency-based aspect extraction; aspect-level scoring pipeline |
| 5. Transformer fine-tune | 8 | FinBERT-class model fine-tuned on financial aspect sentiment |
| 6. Agent layer | 9–10 | Bull/bear/skeptic/judge pipeline in LangGraph with grounding checks |
| 7. Storage + dashboard | 11 | Postgres schema live; Next.js dashboard with drill-down |
| 8. Deployment + monitoring | 12 | Dockerized, deployed on Cloud Run, drift monitor running |
| 9. Evaluation | 13 | Model ladder table, grounding audit, signal validity check |
| 10. Report + demo | 14 | Final report, recorded demo, GitHub polish |

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Transcript/filing sources rate-limit or change format | Build normalization layer defensively; cache raw fetches before parsing |
| Aspect-level labels are expensive to hand-annotate | Annotate a smaller high-quality gold set (a few hundred sentences) for evaluation; use weak/rule-based labels for larger-scale training |
| LLM agent cost scales with watchlist size | Cache aggressively; only re-run the agent layer when new source documents actually arrive for a ticker |
| Signal validity check shows no correlation | Report it as a finding, not a failure — reframe the contribution around the grounding architecture and the lexicon-failure analysis, which stand on their own |
| Scope creep toward a trading system | Explicitly out of scope (Section 3) — keep the report anchored to decision support, not execution |

---

## 12. Ethical & Legal Notes

- This is a research/decision-support tool. All outputs must be clearly labeled as not investment advice.
- Respect `robots.txt` and terms of service for any scraped source; prefer official APIs where available.
- No personally identifiable information is collected; all data sources are public corporate disclosures and news.

---

## 13. Deliverables

1. Deployed service (Cloud Run URL) with working dashboard
2. GitHub repository with full pipeline, Dockerized
3. MLflow experiment log covering the full model ladder
4. Final report covering methodology, evaluation, and honest limitations
5. Short recorded demo (5 minutes) walking through a live brief and its grounding trail
