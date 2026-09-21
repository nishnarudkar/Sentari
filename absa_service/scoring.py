"""Chunk -> aspect mentions -> polarity -> `aspect_scores` rows (+ embeddings)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
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


def score_new_chunks(session: Session, model: SentimentModel, limit: int | None = None) -> dict:
    """Embed + score every chunk that has no score/embedding yet for this model. Idempotent."""
    embedder = get_embedder()
    scored_ids = set(session.scalars(select(AspectScore.chunk_id).where(AspectScore.model_name == model.name)))
    q = select(Chunk, Document).join(Document, Chunk.document_id == Document.id).order_by(Chunk.id)
    stats = {"chunks_seen": 0, "chunks_scored": 0, "scores": 0, "embedded": 0}
    pending_embed: list[Chunk] = []
    for chunk, doc in session.execute(q):
        stats["chunks_seen"] += 1
        if chunk.embedding is None:
            pending_embed.append(chunk)
        if chunk.id in scored_ids or not is_scoreable(chunk):
            continue
        if limit is not None and stats["chunks_scored"] >= limit:
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
    if pending_embed:
        vecs = embedder.embed([c.text for c in pending_embed])
        for c, v in zip(pending_embed, vecs):
            c.embedding = [round(float(x), 5) for x in v]
        stats["embedded"] = len(pending_embed)
    session.commit()
    return stats
