"""Extractor agent: for a ticker + date range, pull the top-k most relevant chunks per aspect.

Relevance = how strongly the chunk expresses the aspect (|score| x confidence, from the ABSA
service) blended with embedding similarity to an aspect query, so the agents argue from the
most informative evidence rather than from arbitrary sentences.
"""
from __future__ import annotations

import datetime as dt
from statistics import mean

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from absa_service.embeddings import get_embedder
from absa_service.schemas import ASPECTS
from agents.state import BriefState, Evidence
from storage.models import AspectScore, Chunk, Document

ASPECT_QUERIES = {
    "guidance": "management guidance and outlook for revenue and earnings",
    "margins": "gross and operating margin, costs, pricing and profitability",
    "demand": "customer demand, orders, backlog, revenue growth and retention",
    "litigation": "litigation, lawsuits, legal and regulatory risk",
    "management_tone": "management confidence, caution and uncertainty",
    "liquidity": "cash, debt, liquidity, credit facility and covenants",
}


def extract(session: Session, ticker: str, start: dt.date, end: dt.date, k: int = 4,
            model_name: str | None = None) -> BriefState:
    q = (select(AspectScore, Chunk, Document)
         .join(Chunk, AspectScore.chunk_id == Chunk.id).join(Document, Chunk.document_id == Document.id)
         .where(AspectScore.ticker == ticker, Document.doc_date >= start, Document.doc_date <= end))
    if model_name:
        q = q.where(AspectScore.model_name == model_name)
    rows = list(session.execute(q))
    embedder = get_embedder()
    query_vecs = {a: embedder.embed([ASPECT_QUERIES[a]])[0] for a in ASPECTS}

    by_aspect: dict[str, list[Evidence]] = {a: [] for a in ASPECTS}
    for sc, ch, doc in rows:
        sim = 0.0
        if ch.embedding:
            sim = float(np.dot(np.asarray(ch.embedding, dtype="float32"), query_vecs[sc.aspect]))
        by_aspect[sc.aspect].append(Evidence(
            chunk_id=ch.id, aspect=sc.aspect, text=ch.text, score=sc.score, confidence=sc.confidence,
            section=ch.section, speaker=ch.speaker, doc_id=doc.id, doc_title=doc.title, doc_type=doc.doc_type,
            doc_date=doc.doc_date.isoformat(), similarity=round(sim, 4)))

    evidence: list[Evidence] = []
    summary: dict[str, dict] = {}
    for aspect, items in by_aspect.items():
        if not items:
            continue
        summary[aspect] = {
            "mean": round(mean(e["score"] for e in items), 4), "n": len(items),
            "positive": sum(e["score"] > 0.15 for e in items), "negative": sum(e["score"] < -0.15 for e in items),
        }
        # top-k on each polarity side so bull and bear both get material to argue from
        ranked = sorted(items, key=lambda e: abs(e["score"]) * (0.5 + e["confidence"]) + 0.3 * e["similarity"],
                        reverse=True)
        pos = [e for e in ranked if e["score"] > 0.15][:k]
        neg = [e for e in ranked if e["score"] < -0.15][:k]
        evidence.extend(pos + neg)
    return BriefState(ticker=ticker, period_start=start, period_end=end, evidence=evidence,
                      aspect_summary=summary, trace=[{"agent": "extractor", "n_evidence": len(evidence),
                                                       "aspect_summary": summary}])
