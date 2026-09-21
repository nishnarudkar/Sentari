"""Skeptic agent: the grounding gate (project.md 5.3).

For every bull/bear claim, verify against the chunks it cites:
  1. citation check   - cited ids exist in the retrieved evidence set
  2. numeric check    - every number in the claim occurs in a cited chunk
  3. similarity check - embedding cosine + content-word overlap between claim and cited text
  4. entailment check - directional consistency (claim polarity vs. the chunk's scored polarity);
                        optionally a real NLI model (SENTARI_NLI=hf, cross-encoder/nli-deberta-v3-small)
Verdicts: `supported` (kept), `unverified` (kept but flagged), `rejected` (stripped from the brief).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

import numpy as np

from absa_service.embeddings import get_embedder
from agents.state import BriefState, Claim, Evidence

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORD_RE = re.compile(r"[a-z][a-z'\-]+")
STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "our", "its", "has", "have",
        "had", "not", "but", "will", "would", "could", "may", "can", "into", "over", "than", "then", "also",
        "management", "said", "supportive", "concerning", "guidance", "margins", "demand", "litigation",
        "liquidity", "tone"}  # framing words the agents add themselves
MIN_SIM, MIN_OVERLAP = 0.12, 0.45
NEG_CUES = re.compile(r"\b(not|no|cannot|unable|fail\w*|declin\w*|decreas\w*|fell|lower\w*|weak\w*|pressure|headwind\w*|"
                      r"adverse|difficult|cut|cutting|withdraw\w*|unfavorable|contract\w*|deteriorat\w*|"
                      r"softness|delay\w*|churn)\b", re.I)
POS_CUES = re.compile(r"\b(strong|record|grew|growth|increas\w*|expand\w*|improv\w*|rais\w*|robust|healthy|"
                      r"confident|optimistic|exceed\w*|favorable|no debt|undrawn|gain\w*|accelerat\w*)\b", re.I)


def numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUM_RE.findall(text)}


def content_words(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if w not in STOP and len(w) > 2}


class NliChecker:
    """Optional transformer NLI (premise=cited chunk, hypothesis=claim). Falls back to None if unavailable."""

    def __init__(self):
        from transformers import pipeline
        self.pipe = pipeline("text-classification", model="cross-encoder/nli-deberta-v3-small", top_k=None)

    def probs(self, premise: str, hypothesis: str) -> dict[str, float]:
        out = self.pipe({"text": premise, "text_pair": hypothesis})
        out = out[0] if out and isinstance(out[0], list) else out
        return {d["label"].lower(): float(d["score"]) for d in out}


@lru_cache(maxsize=1)
def _nli():
    if os.environ.get("SENTARI_NLI") != "hf":
        return None
    try:
        return NliChecker()
    except Exception:  # noqa: BLE001
        return None


def _claim_body(text: str) -> str:
    """Strip the agent's framing prefix ('Margins is supportive (2025-04-24, prepared): ...') before comparing."""
    m = re.search(r'"(.+)"\s*$', text, re.S)
    return m.group(1) if m else text


def check_claim(claim: Claim, evidence_by_id: dict[int, Evidence], embedder=None) -> Claim:
    embedder = embedder or get_embedder()
    diag: dict = {"checks": {}}
    ids = claim.get("cited_chunk_ids") or []
    cited = [evidence_by_id[i] for i in ids if i in evidence_by_id]
    body = _claim_body(claim.get("text", ""))

    # 1. citation
    diag["checks"]["citation"] = bool(cited) and len(cited) == len(ids)
    if not cited:
        return {**claim, "status": "rejected", "support": {**diag, "reason": "no valid citation"}}

    cited_text = " ".join(e["text"] for e in cited)

    # 2. numbers
    claim_nums = numbers(body)
    missing = sorted(n for n in claim_nums if n not in numbers(cited_text))
    diag["checks"]["numbers"] = not missing
    if missing:
        return {**claim, "status": "rejected",
                "support": {**diag, "reason": f"numbers not in cited text: {missing}"}}

    # 3. similarity + overlap
    vecs = embedder.embed([body] + [e["text"] for e in cited])
    sim = float(max(np.dot(vecs[0], v) for v in vecs[1:]))
    cw = content_words(body)
    overlap = len(cw & content_words(cited_text)) / len(cw) if cw else 0.0
    diag.update(similarity=round(sim, 3), overlap=round(overlap, 3))
    diag["checks"]["similarity"] = sim >= MIN_SIM
    diag["checks"]["overlap"] = overlap >= MIN_OVERLAP

    # 4. entailment / direction
    nli = _nli()
    if nli is not None:
        p = nli.probs(cited_text, body)
        diag["nli"] = {k: round(v, 3) for k, v in p.items()}
        entail, contra = p.get("entailment", 0.0), p.get("contradiction", 0.0)
        diag["checks"]["entailment"] = entail >= 0.5
        contradicted = contra >= 0.6
    else:
        claim_neg, claim_pos = bool(NEG_CUES.search(body)), bool(POS_CUES.search(body))
        chunk_score = sum(e["score"] for e in cited) / len(cited)
        # a claim asserting one polarity is contradicted when the scored evidence points firmly the other way
        contradicted = (claim_pos and not claim_neg and chunk_score < -0.3) or (claim_neg and not claim_pos and chunk_score > 0.3)
        # a (near-)verbatim quote cannot contradict its own source; the cue heuristic above is blind to
        # negation ("do NOT expect any material impact"), so exempt quotes instead of rejecting them
        if sim >= 0.8 and overlap >= 0.9:
            contradicted = False
        diag["checks"]["entailment"] = not contradicted
        diag["chunk_score"] = round(chunk_score, 3)
    if contradicted:
        return {**claim, "status": "rejected", "support": {**diag, "reason": "contradicted by cited evidence"}}

    passed = all(diag["checks"].values())
    return {**claim, "status": "supported" if passed else "unverified",
            "support": {**diag, "reason": "ok" if passed else "weak lexical/semantic support"}}


def run(state: BriefState) -> BriefState:
    by_id = {e["chunk_id"]: e for e in state["evidence"]}
    embedder = get_embedder()
    verified: list[Claim] = []
    for claim in state.get("bull_claims", []) + state.get("bear_claims", []):
        verified.append(check_claim(claim, by_id, embedder))
    counts = {s: sum(c["status"] == s for c in verified) for s in ("supported", "unverified", "rejected")}
    return {"verified": verified, "trace": [{"agent": "skeptic", "verdicts": counts, "claims": verified}]}  # type: ignore[return-value]
