"""The daily run: ingest -> score -> (briefs for tickers with new data) -> drift -> digest."""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, select

from absa_service.scoring import score_new_chunks
from absa_service.serving import get_model
from agents.graph import generate_brief
from agents.llm import get_llm
from delivery.digest import deliver
from ingestion.pipeline import load_config, run_from_config
from monitoring.drift import run_drift
from storage.models import Document

log = logging.getLogger(__name__)


def run_daily(session, config: dict | None = None, model_name: str | None = None, send_digest: bool = True) -> dict:
    cfg = config or load_config()
    model = get_model(model_name)
    ingest_stats = run_from_config(session, cfg)
    score_stats = score_new_chunks(session, model)

    briefs = []
    llm = get_llm()
    for ticker in cfg["watchlist"]:
        bounds = session.execute(select(func.min(Document.doc_date), func.max(Document.doc_date))
                                 .where(Document.ticker == ticker)).one()
        if bounds[0] is None:
            continue
        # fingerprinting inside generate_brief makes this a no-op unless new data arrived
        brief = generate_brief(session, ticker, bounds[0], bounds[1], llm=llm, model_name=model.name)
        briefs.append({"ticker": ticker, "brief_id": brief.id, "confidence": brief.confidence})

    latest = session.scalar(select(func.max(Document.doc_date))) or dt.date.today()
    drift = run_drift(session, cfg["watchlist"], as_of=latest, model_name=model.name)
    digest = deliver(session, cfg["watchlist"], [d for d in drift if d["alert"]]) if send_digest else None
    return {"ingest": ingest_stats.__dict__, "scoring": score_stats, "briefs": briefs, "drift": drift,
            "digest": digest, "model": model.name}
