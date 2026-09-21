"""FastAPI app: ABSA endpoints + dashboard/read API + daily-run trigger.

    uvicorn absa_service.main:app --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from absa_service.schemas import ASPECTS, Item
from absa_service.scoring import analyze_sentence
from absa_service.serving import get_model
from ingestion.normalize import split_sentences
from storage.db import get_engine, init_db, make_session_factory
from storage.models import ModelRun

DISCLAIMER = ("Sentari is a research and decision-support tool. Nothing it produces is investment advice, "
              "a recommendation, or a prediction of price movements.")


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    model: str | None = None


class ScoreItem(BaseModel):
    text: str
    aspect: str


class ScoreRequest(BaseModel):
    items: list[ScoreItem] = Field(..., max_length=500)
    model: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    yield


app = FastAPI(title="Sentari", version="0.1.0", lifespan=lifespan,
              description=DISCLAIMER)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


def get_session():
    session = app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def resolve_model(name: str | None):
    try:
        return get_model(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok", "aspects": ASPECTS, "disclaimer": DISCLAIMER}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Aspect-level sentiment for free text (sentence-split, each sentence analysed)."""
    model = resolve_model(req.model)
    results = []
    for sent in split_sentences(req.text):
        for r in analyze_sentence(model, sent):
            results.append({"sentence": sent, **r})
    return {"model": model.name, "results": results, "disclaimer": DISCLAIMER}


@app.post("/score")
def score(req: ScoreRequest):
    """Raw polarity for (text, aspect) pairs - the same interface every ladder model implements."""
    model = resolve_model(req.model)
    bad = [i.aspect for i in req.items if i.aspect not in ASPECTS]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown aspects: {sorted(set(bad))}")
    preds = model.predict([Item(text=i.text, aspect=i.aspect, sentence=i.text) for i in req.items])
    return {"model": model.name, "predictions": [
        {"label": p.label, "score": p.score, "confidence": p.confidence, "probs": p.probs} for p in preds]}


@app.get("/models")
def models(session: Session = Depends(get_session)):
    rows = session.scalars(select(ModelRun).order_by(ModelRun.id.desc()).limit(50))
    return [{"name": r.name, "version": r.version, "serving": r.serving, "mlflow_run_id": r.mlflow_run_id,
             "metrics": r.metrics, "created_at": r.created_at.isoformat()} for r in rows]


# read API for the dashboard is registered from api.py (kept separate for readability)
from absa_service import api as _api  # noqa: E402

app.include_router(_api.router)
