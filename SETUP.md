# Setup: what Sentari needs and how to get it

Configuration lives in a local `.env` (copy [.env.example](.env.example); it is gitignored). Real environment variables always
override the file. **Never paste keys into chat, commits, or issues.** Everything below except the first section is optional:
with no `.env`, Sentari runs on the bundled synthetic sample data, SQLite, and offline agents.

## 1. Required to build/run anything real

| Item | Why | How to get it |
|---|---|---|
| Python 3.12+ and Node 20+ | backend / dashboard | python.org, nodejs.org |
| `pip install -r requirements.txt` then `python -m spacy download en_core_web_sm` | NLP stack | — |
| `SENTARI_USER_AGENT="Your Name your@email"` | SEC EDGAR refuses requests without a contact User-Agent | No signup. Choose a contact you are happy to expose to the SEC |

## 2. Real earnings-call transcripts (the main gap today)

The only transcript source in the repo is synthetic. EDGAR gives 10-K/10-Q text but not call transcripts, so a real source
must be chosen; I will build the scraper for whichever you pick. Options, cheapest first (verify current terms/pricing yourself; I
have not tested any of them):

1. **Public datasets** (no key): search Kaggle / Hugging Face for "earnings call transcripts". Good for history and for
   building a real gold set. Check each dataset's licence and that coverage matches your tickers/dates.
2. **Indian companies (NSE/BSE):** listed companies must file call transcripts with the exchanges (SEBI LODR), usually as
   PDFs on the company's BSE/NSE announcements page. Free, needs a PDF-text extractor (I can add one) and respect for the
   exchange's terms of use.
3. **Company IR pages:** free, per-company scraping, brittle; respect robots.txt.
4. **Paid/freemium APIs** (Financial Modeling Prep, Finnhub, API Ninjas, Alpha Vantage, etc.): sign up on their site, create
   an API key in the dashboard, and check which plan actually includes the transcripts endpoint. Put the key in
   `TRANSCRIPT_API_KEY` (reserved; wired up when the scraper is written).

Also tell me your **pilot watchlist** (project.md: 10 tickers; US and/or NSE/BSE).

## 3. LLM agents (optional, recommended for the final demo)

`ANTHROPIC_API_KEY`: https://console.anthropic.com -> API keys. Requires prepaid credit; set a monthly spend limit. Without it the
bull/bear/judge text comes from the offline heuristic backend. With it, `python -m evaluation.latency_cost` reports real tokens
and USD per brief (project.md §7.5). Set `SENTARI_LLM=heuristic` to force offline.

## 4. Better evaluation (recommended)

* **Official Loughran-McDonald dictionary** (free for academic use): https://sraf.nd.edu/loughranmcdonald-master-dictionary/ ->
  download the Master Dictionary CSV -> save as `data/lexicons/Loughran-McDonald_MasterDictionary.csv`. It is gitignored
  (`data/lexicons/*.csv`) so it is not redistributed through the repo.
* **Real gold set:** annotate a few hundred sentences from real filings/transcripts into `data/gold/gold.tsv`
  (`aspect<TAB>label<TAB>trap<TAB>sentence`, labels `positive|negative|neutral`). This needs your time; it is what makes the model
  comparison credible.
* **Human grounding audit:** `python -m evaluation.grounding_audit --export 50`, fill `human_supported` with 1/0 for each claim, then
  `--score` the CSV.
* **Signal validity:** free price data via `pip install yfinance` then `python -m evaluation.signal_validity --fetch`, or supply your
  own `ticker,date,ret_5d` CSV. Needs real transcripts first.
* Optional: `SENTARI_NLI=hf` (Skeptic uses a transformer NLI model; strongly recommended, see README audit), GloVe vectors
  (`SENTARI_GLOVE`, https://nlp.stanford.edu/projects/glove/, `glove.6B.zip` is ~800 MB).

## 5. Digest delivery (optional)

* **Slack:** https://api.slack.com/apps -> Create New App -> Incoming Webhooks -> Add New Webhook to Workspace -> copy the URL into
  `SLACK_WEBHOOK_URL`.
* **Email (SMTP):** for Gmail, enable 2-step verification, create an App Password (Google Account -> Security), then set
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO`.

## 6. Deployment (project.md deliverable 1)

* Docker Desktop running (to build-test the images locally): https://www.docker.com/products/docker-desktop/
* A **Google Cloud project with billing enabled**, the `gcloud` CLI (https://cloud.google.com/sdk/docs/install) and `gcloud auth login`.
  New accounts usually get trial credit; Cloud Run/Cloud SQL still need a billing account attached.
* A Postgres `DATABASE_URL` (Cloud SQL, see [deploy/README.md](deploy/README.md), or local via `docker compose up postgres`).
* `SENTARI_CRON_TOKEN`: any random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
* Dashboard: `dashboard/.env.local` with `NEXT_PUBLIC_API_URL=<your API URL>` (baked in at build time).

## Quick check that config is picked up

```bash
python -c "import sentari_env, os; print('loaded from', sentari_env.env_path(), 'exists:', sentari_env.env_path().is_file())"
```
