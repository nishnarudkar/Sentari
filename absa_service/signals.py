"""Time-series signals from aspect scores, incl. the platform's signature
prepared-remarks vs Q&A delta (project.md 5.2).

delta(aspect) = mean(score | Q&A) - mean(score | prepared)
A negative delta means management sounds worse when unscripted than in the script.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from storage.models import AspectScore, Chunk, Document


def document_aspect_summary(session: Session, document_id: int, model_name: str | None = None) -> dict:
    q = (select(AspectScore, Chunk).join(Chunk, AspectScore.chunk_id == Chunk.id)
         .where(Chunk.document_id == document_id))
    if model_name:
        q = q.where(AspectScore.model_name == model_name)
    by_aspect: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for sc, ch in session.execute(q):
        by_aspect[sc.aspect][ch.section].append(sc.score)
        by_aspect[sc.aspect]["all"].append(sc.score)
    out: dict[str, dict] = {}
    for aspect, secs in by_aspect.items():
        prepared, qa = secs.get("prepared", []), secs.get("qa", [])
        out[aspect] = {
            "mean": round(mean(secs["all"]), 4), "n": len(secs["all"]),
            "prepared": round(mean(prepared), 4) if prepared else None, "n_prepared": len(prepared),
            "qa": round(mean(qa), 4) if qa else None, "n_qa": len(qa),
            "delta": round(mean(qa) - mean(prepared), 4) if prepared and qa else None,
        }
    return out


def transcript_delta(session: Session, document_id: int, model_name: str | None = None) -> float | None:
    """Single scalar for the doc: average per-aspect Q&A-minus-prepared gap (aspects with both sections)."""
    deltas = [v["delta"] for v in document_aspect_summary(session, document_id, model_name).values()
              if v["delta"] is not None]
    return round(mean(deltas), 4) if deltas else None


def document_level_sentiment(session: Session, document_id: int, model_name: str | None = None) -> float | None:
    """The 'naive' comparator: plain average of every aspect score in the doc (no section split)."""
    summ = document_aspect_summary(session, document_id, model_name)
    vals = [v["mean"] for v in summ.values()]
    return round(mean(vals), 4) if vals else None


def aspect_trajectory(session: Session, ticker: str, aspect: str, model_name: str | None = None) -> list[dict]:
    """Per-document mean score for a (ticker, aspect), oldest first - the dashboard's trajectory chart."""
    q = (select(AspectScore, Document.id, Document.doc_type, Document.title)
         .join(Chunk, AspectScore.chunk_id == Chunk.id).join(Document, Chunk.document_id == Document.id)
         .where(AspectScore.ticker == ticker, AspectScore.aspect == aspect))
    if model_name:
        q = q.where(AspectScore.model_name == model_name)
    docs: dict[int, dict] = {}
    for sc, doc_id, doc_type, title in session.execute(q):
        d = docs.setdefault(doc_id, {"document_id": doc_id, "date": sc.doc_date.isoformat(), "doc_type": doc_type,
                                     "title": title, "scores": [], "prepared": [], "qa": []})
        d["scores"].append(sc.score)
        if sc.section in ("prepared", "qa"):
            d[sc.section].append(sc.score)
    out = []
    for d in sorted(docs.values(), key=lambda x: x["date"]):
        out.append({
            "document_id": d["document_id"], "date": d["date"], "doc_type": d["doc_type"], "title": d["title"],
            "mean": round(mean(d["scores"]), 4), "n": len(d["scores"]),
            "prepared": round(mean(d["prepared"]), 4) if d["prepared"] else None,
            "qa": round(mean(d["qa"]), 4) if d["qa"] else None,
        })
    return out
