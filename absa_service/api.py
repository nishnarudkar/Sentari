"""Read API used by the dashboard (watchlist, trajectories, drill-down, briefs, drift, digest)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from absa_service.schemas import ASPECTS
from absa_service.signals import aspect_trajectory, document_aspect_summary
from storage.models import AgentTrace, AspectScore, Brief, Chunk, Document, DriftReport

router = APIRouter()

DISCLAIMER = "Research and decision-support only. Not investment advice."


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


class BriefRequest(BaseModel):
    ticker: str
    start: dt.date | None = None
    end: dt.date | None = None
    force: bool = False


@router.get("/watchlist")
def watchlist(session: Session = Depends(get_session)):
    tickers = session.scalars(select(Document.ticker).distinct().order_by(Document.ticker)).all()
    out = []
    for t in tickers:
        latest_doc = session.scalars(select(Document).where(Document.ticker == t, Document.doc_type == "transcript")
                                     .order_by(Document.doc_date.desc())).first() \
            or session.scalars(select(Document).where(Document.ticker == t).order_by(Document.doc_date.desc())).first()
        aspects = document_aspect_summary(session, latest_doc.id) if latest_doc else {}
        brief = session.scalars(select(Brief).where(Brief.ticker == t).order_by(Brief.id.desc())).first()
        out.append({
            "ticker": t, "latest_document": {"id": latest_doc.id, "title": latest_doc.title,
                                             "date": latest_doc.doc_date.isoformat()} if latest_doc else None,
            "aspects": aspects,
            "brief": {"id": brief.id, "confidence": brief.confidence, "stance": brief.body.get("stance"),
                      "summary": brief.summary, "created_at": brief.created_at.isoformat()} if brief else None,
        })
    return {"tickers": out, "disclaimer": DISCLAIMER}


@router.get("/tickers/{ticker}/trajectory")
def trajectory(ticker: str, model: str | None = None, session: Session = Depends(get_session)):
    ticker = ticker.upper()
    return {"ticker": ticker, "aspects": {a: aspect_trajectory(session, ticker, a, model) for a in ASPECTS},
            "disclaimer": DISCLAIMER}


@router.get("/tickers/{ticker}/points")
def points(ticker: str, aspect: str, document_id: int | None = None, model: str | None = None,
           limit: int = Query(200, le=1000), session: Session = Depends(get_session)):
    """Individual scored sentences behind a trajectory data point (drill-down)."""
    q = (select(AspectScore, Chunk, Document).join(Chunk, AspectScore.chunk_id == Chunk.id)
         .join(Document, Chunk.document_id == Document.id)
         .where(AspectScore.ticker == ticker.upper(), AspectScore.aspect == aspect))
    if document_id:
        q = q.where(Document.id == document_id)
    if model:
        q = q.where(AspectScore.model_name == model)
    q = q.order_by(Document.doc_date, Chunk.idx).limit(limit)
    return [{"chunk_id": ch.id, "text": ch.text, "section": ch.section, "speaker": ch.speaker,
             "date": doc.doc_date.isoformat(), "document": doc.title, "document_id": doc.id,
             "score": sc.score, "polarity": sc.polarity, "confidence": sc.confidence, "model": sc.model_name}
            for sc, ch, doc in session.execute(q)]


@router.get("/chunks/{chunk_id}")
def chunk_detail(chunk_id: int, context: int = 2, session: Session = Depends(get_session)):
    chunk = session.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(404, "chunk not found")
    doc = session.get(Document, chunk.document_id)
    neighbours = session.scalars(select(Chunk).where(
        Chunk.document_id == doc.id, Chunk.idx >= chunk.idx - context, Chunk.idx <= chunk.idx + context)
        .order_by(Chunk.idx)).all()
    scores = session.scalars(select(AspectScore).where(AspectScore.chunk_id == chunk_id)).all()
    return {
        "chunk": {"id": chunk.id, "text": chunk.text, "section": chunk.section, "speaker": chunk.speaker},
        "document": {"id": doc.id, "title": doc.title, "type": doc.doc_type, "date": doc.doc_date.isoformat(),
                     "source": doc.source, "url": doc.source_url},
        "context": [{"id": c.id, "text": c.text, "speaker": c.speaker, "is_target": c.id == chunk_id} for c in neighbours],
        "scores": [{"aspect": s.aspect, "polarity": s.polarity, "score": s.score, "confidence": s.confidence,
                    "model": s.model_name, "model_version": s.model_version} for s in scores],
    }


def _brief_json(b: Brief, with_traces: bool = False, session: Session | None = None) -> dict:
    out = {"id": b.id, "ticker": b.ticker, "period": [b.period_start.isoformat(), b.period_end.isoformat()],
           "summary": b.summary, "confidence": b.confidence, "body": b.body, "tokens_in": b.tokens_in,
           "tokens_out": b.tokens_out, "latency_s": b.latency_s, "created_at": b.created_at.isoformat()}
    if with_traces and session is not None:
        traces = session.scalars(select(AgentTrace).where(AgentTrace.brief_id == b.id).order_by(AgentTrace.step))
        out["traces"] = [{"step": t.step, "agent": t.agent, "payload": t.payload} for t in traces]
    return out


@router.get("/tickers/{ticker}/briefs")
def ticker_briefs(ticker: str, session: Session = Depends(get_session)):
    rows = session.scalars(select(Brief).where(Brief.ticker == ticker.upper()).order_by(Brief.id.desc()).limit(20))
    return [_brief_json(b) for b in rows]


@router.get("/briefs/{brief_id}")
def brief_detail(brief_id: int, session: Session = Depends(get_session)):
    b = session.get(Brief, brief_id)
    if b is None:
        raise HTTPException(404, "brief not found")
    out = _brief_json(b, with_traces=True, session=session)
    # resolve every cited chunk id to its source sentence so the UI can drill down in one request
    cited = {cid for sents in b.body.get("summary", []) for cid in sents.get("citations", [])}
    for sect in b.body.get("sections", {}).values():
        for side in sect.values():
            for s in side:
                cited.update(s.get("citations", []))
    for s in b.body.get("unverified", []):
        cited.update(s.get("citations", []))
    rows = session.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
                           .where(Chunk.id.in_(cited))) if cited else []
    out["sources"] = {ch.id: {"text": ch.text, "section": ch.section, "speaker": ch.speaker,
                              "document": doc.title, "date": doc.doc_date.isoformat(), "document_id": doc.id}
                      for ch, doc in rows}
    return out


@router.post("/briefs/generate")
def generate(req: BriefRequest, session: Session = Depends(get_session)):
    from agents.graph import generate_brief
    ticker = req.ticker.upper()
    bounds = session.execute(select(func.min(Document.doc_date), func.max(Document.doc_date))
                             .where(Document.ticker == ticker)).one()
    if bounds[0] is None:
        raise HTTPException(404, f"no documents for {ticker}")
    brief = generate_brief(session, ticker, req.start or bounds[0], req.end or bounds[1], force=req.force)
    return _brief_json(brief)


@router.get("/drift")
def drift(ticker: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    q = select(DriftReport).order_by(DriftReport.id.desc()).limit(limit)
    if ticker:
        q = select(DriftReport).where(DriftReport.ticker == ticker.upper()).order_by(DriftReport.id.desc()).limit(limit)
    return [{"ticker": r.ticker, "week_start": r.week_start.isoformat(), "psi_aspect_mix": r.psi_aspect_mix,
             "confidence_shift": r.confidence_shift, "alert": r.alert, "detail": r.detail,
             "created_at": r.created_at.isoformat()} for r in session.scalars(q)]


@router.get("/digest")
def digest(session: Session = Depends(get_session)):
    from delivery.digest import render_text, top_moves
    tickers = session.scalars(select(Document.ticker).distinct()).all()
    moves = top_moves(session, tickers)
    return {"moves": moves, "text": render_text(moves)}


@router.post("/run/daily")
def run_daily_endpoint(request: Request, session: Session = Depends(get_session)):
    """Target of Cloud Scheduler (see deploy/). Idempotent: re-running does not duplicate data.
    If SENTARI_CRON_TOKEN is set, callers must send it in the X-Cron-Token header."""
    import os
    token = os.environ.get("SENTARI_CRON_TOKEN")
    if token and request.headers.get("X-Cron-Token") != token:
        raise HTTPException(401, "invalid cron token")
    from absa_service.orchestration import run_daily
    return run_daily(session, send_digest=True)
