# Deploying to Google Cloud Run

Two services (API and dashboard) plus a Cloud Scheduler job. Commands are provided as a script but were
**not executed from this repository's CI** - they need your GCP project and billing.

```bash
export PROJECT=<gcp-project> REGION=us-central1
gcloud config set project $PROJECT

# 1. Postgres (Cloud SQL) - create once, then set DATABASE_URL below
gcloud sql instances create sentari-db --database-version=POSTGRES_16 --tier=db-f1-micro --region=$REGION
gcloud sql databases create sentari --instance=sentari-db

# 2. Build & deploy the API
gcloud run deploy sentari-api --source . --region=$REGION --allow-unauthenticated \
  --memory=2Gi --cpu=2 --timeout=900 \
  --set-env-vars=DATABASE_URL=postgresql+psycopg2://USER:PASS@/sentari?host=/cloudsql/$PROJECT:$REGION:sentari-db \
  --set-env-vars=SENTARI_CRON_TOKEN=<random>,CORS_ORIGINS=https://<dashboard-url> \
  --add-cloudsql-instances=$PROJECT:$REGION:sentari-db
# optional LLM agents / digest: --set-secrets=ANTHROPIC_API_KEY=anthropic-key:latest,SLACK_WEBHOOK_URL=slack:latest

# 3. Dashboard (API URL is baked in at build time)
API_URL=$(gcloud run services describe sentari-api --region=$REGION --format='value(status.url)')
gcloud run deploy sentari-dashboard --source dashboard --region=$REGION --allow-unauthenticated \
  --build-env-vars=NEXT_PUBLIC_API_URL=$API_URL

# 4. Daily schedule (see ingestion/scheduler_config.yaml) - hits POST /run/daily with the shared token
gcloud scheduler jobs create http sentari-daily --location=$REGION --schedule="30 6 * * 1-5" --time-zone=UTC \
  --uri="$API_URL/run/daily" --http-method=POST --headers="X-Cron-Token=<random>" --attempt-deadline=900s
```

Notes
* The image falls back to the rule-based `lm_directional` model unless trained weights are baked in
  (`COPY artifacts/models`) or mounted; FinBERT weights are ~440 MB, so prefer a GCS mount or a min-instances=1 service.
* `/run/daily` is idempotent (documents are hashed, briefs are fingerprinted), so Scheduler retries are safe.
* The dashboard is public by default; put IAP / Cloud Run auth in front of it for anything beyond a demo.
