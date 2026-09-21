# Backend image (FastAPI: ABSA service + read API + daily run). Deployed to Cloud Run.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# CPU-only torch keeps the image small; transformers is only needed for the finbert_ft model
COPY requirements.txt requirements-extra.txt ./
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch \
 && grep -v '^torch' requirements.txt | pip install -r /dev/stdin \
 && pip install langgraph anthropic transformers psycopg2-binary scipy \
 && python -m spacy download en_core_web_sm \
 && python -c "import nltk; [nltk.download(p, quiet=True) for p in ('wordnet','sentiwordnet','omw-1.4')]"

COPY absa_service ./absa_service
COPY agents ./agents
COPY ingestion ./ingestion
COPY storage ./storage
COPY monitoring ./monitoring
COPY delivery ./delivery
COPY evaluation ./evaluation
COPY data ./data
# trained weights are optional: `COPY artifacts/models` when baking a model into the image
# (otherwise the service falls back to the rule-based lm_directional model)

RUN useradd -m sentari && chown -R sentari /app
USER sentari

ENV PORT=8080 DATABASE_URL=sqlite:////tmp/sentari.db
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",\"8080\")}/health')"
CMD ["sh", "-c", "uvicorn absa_service.main:app --host 0.0.0.0 --port ${PORT}"]
