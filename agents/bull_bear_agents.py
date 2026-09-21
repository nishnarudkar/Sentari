"""Bull and Bear agents: build the strongest case from *extracted, scored* evidence.

Every claim must cite chunk ids. With a generative LLM the claims are written by the model
(prompted to quote/paraphrase only what the cited chunks say); the offline heuristic backend
composes claims directly from the top-scored chunks. Either way the Skeptic re-verifies each
claim, so a weak generator can lower coverage but not introduce ungrounded statements into a brief.
"""
from __future__ import annotations

import re

from absa_service.schemas import ASPECTS
from agents.llm import LLM
from agents.state import BriefState, Claim, Evidence

ID_PREFIX = {"bull": "bl", "bear": "br"}  # must be distinct: claim ids key the brief and the audit trail
ASPECT_LABEL = {"guidance": "Guidance", "margins": "Margins", "demand": "Demand", "litigation": "Litigation",
                "management_tone": "Management tone", "liquidity": "Liquidity"}

SYSTEM = """You are the {side} analyst in an earnings-intelligence pipeline. Build the strongest {side_desc} case
for {ticker} using ONLY the numbered evidence below. Rules:
- Every claim must cite one or more evidence ids and must be fully supported by those sentences.
- Do not add facts, numbers or causes that are not in the cited evidence.
- Prefer claims about guidance, margins, demand, litigation, management tone and liquidity.
- Return JSON: {{"claims": [{{"aspect": "<aspect>", "text": "<claim>", "cited_chunk_ids": [<id>, ...]}}]}}
- At most {max_claims} claims. No commentary outside the JSON."""


def _format_evidence(evidence: list[Evidence]) -> str:
    return "\n".join(f'[{e["chunk_id"]}] ({e["aspect"]}, {e["doc_date"]}, {e["section"]}, score {e["score"]:+.2f}) '
                     f'{e["text"]}' for e in evidence)


def _clean_quote(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def heuristic_claims(side: str, evidence: list[Evidence], max_claims: int) -> list[Claim]:
    want_positive = side == "bull"
    picks: list[Evidence] = []
    for aspect in ASPECTS:  # one strongest sentence per aspect first, then fill by strength
        cand = [e for e in evidence if e["aspect"] == aspect and (e["score"] > 0.15 if want_positive else e["score"] < -0.15)]
        if cand:
            picks.append(max(cand, key=lambda e: abs(e["score"]) * (0.5 + e["confidence"])))
    picks = sorted(picks, key=lambda e: abs(e["score"]), reverse=True)[:max_claims]
    claims: list[Claim] = []
    for i, e in enumerate(picks, 1):
        tone = "supportive" if want_positive else "concerning"
        claims.append(Claim(id=f"{ID_PREFIX[side]}{i}", side=side, aspect=e["aspect"],
                            text=f'{ASPECT_LABEL[e["aspect"]]} is {tone} ({e["doc_date"]}, {e["section"]}): '
                                 f'"{_clean_quote(e["text"])}"',
                            cited_chunk_ids=[e["chunk_id"]]))
    return claims


def llm_claims(llm: LLM, side: str, state: BriefState, max_claims: int) -> list[Claim]:
    want_positive = side == "bull"
    ev = [e for e in state["evidence"] if (e["score"] > 0.15 if want_positive else e["score"] < -0.15)]
    if not ev:
        return []
    system = SYSTEM.format(side=side, side_desc="bullish" if want_positive else "bearish",
                           ticker=state["ticker"], max_claims=max_claims)
    data = llm.complete_json(system, "EVIDENCE:\n" + _format_evidence(ev))
    claims: list[Claim] = []
    for i, c in enumerate(data.get("claims", [])[:max_claims], 1):
        ids = [int(x) for x in c.get("cited_chunk_ids", []) if str(x).lstrip("-").isdigit()]
        claims.append(Claim(id=f"{ID_PREFIX[side]}{i}", side=side, aspect=c.get("aspect", ""),
                            text=str(c.get("text", "")).strip(), cited_chunk_ids=ids))
    return claims


def run_side(side: str, state: BriefState, llm: LLM, max_claims: int = 6) -> BriefState:
    if llm.is_generative:
        claims = llm_claims(llm, side, state, max_claims)
    else:
        claims = heuristic_claims(side, state["evidence"], max_claims)
    key = f"{side}_claims"
    return {key: claims, "trace": [{"agent": side, "claims": claims}]}  # type: ignore[return-value]
