"""Chunk -> aspect mentions -> polarity -> `aspect_scores` rows (+ embeddings)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from absa_service.aspect_extraction import extract_mentions
from absa_service.embeddings import get_embedder
from absa_service.models.base import SentimentModel
from absa_service.schemas import Item, Prediction
from storage.models import AspectScore, Chunk, Document

# speakers we never score: the operator only reads boilerplate; analysts' questions are not company claims
SKIP_SPEAKER_HINTS = ("operator",)


def analyze_sentence(model: SentimentModel, sentence: str, use_spacy: bool = True) -> list[dict]:
    """Score a sentence: one entry per aspect (clauses of the same aspect are averaged)."""
    mentions = extract_mentions(sentence, use_spacy=use_spacy)
    if not mentions:
        return []
    items = [Item(text=m.clause, aspect=m.aspect, sentence=sentence, opinion_words=m.opinion_words) for m in mentions]
    preds = model.predict(items)
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for m, p in zip(mentions, preds):
        grouped[m.aspect].append((m, p))
    out = []
    for aspect, pairs in grouped.items():
        score = sum(p.score for _, p in pairs) / len(pairs)
        conf = sum(p.confidence for _, p in pairs) / len(pairs)
        best = max(pairs, key=lambda mp: abs(mp[1].score))
        label = "positive" if score > 0.15 else "negative" if score < -0.15 else best[1].label if abs(score) > 0.05 else "neutral"
        out.append({
            "aspect": aspect, "polarity": label, "score": round(score, 4), "confidence": round(conf, 4),
            "trigger": best[0].trigger, "clause": best[0].clause, "opinion_words": best[0].opinion_words,
            "negated": best[0].negated, "hedge": best[0].hedge,
        })
    return out


def is_scoreable(chunk: Chunk) -> bool:
    spk = (chunk.speaker or "").lower()
    if any(h in spk for h in SKIP_SPEAKER_HINTS):
        return False
    if "analyst" in spk and chunk.section == "qa":
        return False  # analysts ask; we score what *management* says
    return True


def score_new_chunks(session: Session, model: SentimentModel) -> dict:
    """Score every not-yet-analysed document with `model`, then embed the chunks that carry aspect scores.

    A document counts as analysed once this model has scored any of its chunks (documents are scored in one
    pass), so chunks without aspect mentions are not re-analysed on every run. Only chunks with aspect scores
    are embedded: they are the only ones the Extractor retrieves, and embedding every sentence of a real call
    corpus multiplied the database size (~75% of sentences carry no aspect). Idempotent."""
    done_docs = set(session.scalars(
        select(Chunk.document_id).join(AspectScore, AspectScore.chunk_id == Chunk.id)
        .where(AspectScore.model_name == model.name).distinct()))
    q = (select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
         .where(Document.id.not_in(done_docs) if done_docs else true()).order_by(Chunk.id))
    stats = {"chunks_seen": 0, "chunks_scored": 0, "scores": 0, "embedded": 0}
    for chunk, doc in session.execute(q):
        stats["chunks_seen"] += 1
        if not is_scoreable(chunk):
            continue
        results = analyze_sentence(model, chunk.text)
        stats["chunks_scored"] += 1
        for r in results:
            session.add(AspectScore(
                chunk_id=chunk.id, aspect=r["aspect"], polarity=r["polarity"], score=r["score"],
                confidence=r["confidence"], model_name=model.name, model_version=model.version,
                ticker=doc.ticker, doc_date=doc.doc_date, section=chunk.section,
            ))
            stats["scores"] += 1
    session.flush()
    pending = list(session.scalars(select(Chunk).where(
        Chunk.embedding.is_(None), Chunk.id.in_(select(AspectScore.chunk_id).distinct())).order_by(Chunk.id)))
    embedder = get_embedder()
    for i in range(0, len(pending), 2000):
        batch = pending[i:i + 2000]
        for c, v in zip(batch, embedder.embed([c.text for c in batch])):
            c.embedding = [round(float(x), 4) for x in v]
    stats["embedded"] = len(pending)
    session.commit()
    return stats
