"""Judge agent: assembles the final brief from claims that survived the Skeptic.

The brief is *constructed from verified claims only*: rejected claims never appear, unverified ones
are shown in a separate flagged list. Confidence is a transparent heuristic (not a calibrated
probability):

    confidence = 0.5 * weighted_survival + 0.3 * mean_evidence_confidence + 0.2 * aspect_coverage
    weighted_survival = (supported + 0.4 * unverified) / total_claims
"""
from __future__ import annotations

from statistics import mean

from absa_service.schemas import ASPECTS
from agents.bull_bear_agents import ASPECT_LABEL
from agents.llm import LLM
from agents.state import BriefState, Claim

DISCLAIMER = "Research and decision-support only. Not investment advice."
UNVERIFIED_WEIGHT = 0.4


def stance_from_scores(aspect_summary: dict[str, dict]) -> tuple[str, float]:
    if not aspect_summary:
        return "insufficient data", 0.0
    net = mean(v["mean"] for v in aspect_summary.values())
    label = "leaning positive" if net > 0.2 else "leaning negative" if net < -0.2 else "mixed"
    return label, round(net, 3)


def compute_confidence(state: BriefState, claims: list[Claim]) -> tuple[float, dict]:
    total = len(claims)
    sup = sum(c["status"] == "supported" for c in claims)
    unv = sum(c["status"] == "unverified" for c in claims)
    survival = (sup + UNVERIFIED_WEIGHT * unv) / total if total else 0.0
    ev = state.get("evidence", [])
    mean_conf = mean(e["confidence"] for e in ev) if ev else 0.0
    coverage = len({c["aspect"] for c in claims if c["status"] != "rejected"}) / len(ASPECTS)
    conf = 0.5 * survival + 0.3 * mean_conf + 0.2 * coverage
    return round(min(1.0, conf), 3), {"survival": round(survival, 3), "mean_evidence_confidence": round(mean_conf, 3),
                                       "aspect_coverage": round(coverage, 3), "supported": sup, "unverified": unv,
                                       "rejected": total - sup - unv}


def _sentence(claim: Claim) -> dict:
    return {"text": claim["text"], "aspect": claim["aspect"], "side": claim["side"], "claim_id": claim["id"],
            "citations": claim["cited_chunk_ids"], "status": claim["status"]}


def _template_summary(ticker: str, stance: str, net: float, sup: list[Claim], deltas: dict) -> list[dict]:
    sentences = [{"text": f"{ticker}: aspect sentiment over the period is {stance} (net {net:+.2f}).", "citations": [],
                  "claim_id": None}]
    for side, verb in (("bull", "Supporting"), ("bear", "Concerning")):
        for c in [x for x in sup if x["side"] == side][:3]:
            sentences.append({"text": f"{verb} {ASPECT_LABEL.get(c['aspect'], c['aspect']).lower()}: {c['text']}",
                              "citations": c["cited_chunk_ids"], "claim_id": c["id"]})
    if deltas:
        worst = min(deltas.items(), key=lambda kv: kv[1])
        if worst[1] < -0.3:
            sentences.append({"text": f"Management sounded weaker in unscripted Q&A than in prepared remarks "
                                      f"(transcript {worst[0]}: Q&A minus prepared = {worst[1]:+.2f}).",
                              "citations": [], "claim_id": None})
    return sentences


def run(state: BriefState, llm: LLM) -> BriefState:
    claims = state.get("verified", [])
    supported = [c for c in claims if c["status"] == "supported"]
    unverified = [c for c in claims if c["status"] == "unverified"]
    rejected = [c for c in claims if c["status"] == "rejected"]
    stance, net = stance_from_scores(state.get("aspect_summary", {}))
    conf, conf_detail = compute_confidence(state, claims)
    deltas = state.get("signals", {}).get("transcript_deltas", {})

    summary_sentences = _template_summary(state["ticker"], stance, net, supported, deltas)
    if llm.is_generative and supported:
        summary_sentences = _llm_summary(llm, state, stance, net, supported, deltas) or summary_sentences

    by_aspect: dict[str, dict[str, list[dict]]] = {}
    for c in supported:
        by_aspect.setdefault(c["aspect"], {"bull": [], "bear": []})[c["side"]].append(_sentence(c))
    brief = {
        "ticker": state["ticker"], "period": [state["period_start"].isoformat(), state["period_end"].isoformat()],
        "stance": stance, "net_sentiment": net, "confidence": conf, "confidence_detail": conf_detail,
        "summary": summary_sentences, "sections": by_aspect,
        "unverified": [_sentence(c) for c in unverified],
        "dropped_claims": len(rejected), "aspect_summary": state.get("aspect_summary", {}),
        "signals": state.get("signals", {}), "disclaimer": DISCLAIMER,
    }
    return {"brief": brief, "trace": [{"agent": "judge", "confidence": conf, "detail": conf_detail}]}  # type: ignore[return-value]


JUDGE_SYSTEM = """You are the judge in an earnings-intelligence pipeline. Write a 3-5 sentence brief for {ticker}
using ONLY the verified claims below. Every sentence must end with the claim ids it relies on in square
brackets, e.g. [bl1,br2]. Do not introduce facts that are not in the claims. Return JSON:
{{"sentences": [{{"text": "...", "claim_ids": ["bl1"]}}]}}"""


def _llm_summary(llm: LLM, state: BriefState, stance: str, net: float, supported: list[Claim], deltas: dict):
    ids = {c["id"]: c for c in supported}
    listing = "\n".join(f'{c["id"]} ({c["side"]}, {c["aspect"]}): {c["text"]}' for c in supported)
    data = llm.complete_json(JUDGE_SYSTEM.format(ticker=state["ticker"]),
                             f"Net aspect sentiment: {net:+.2f} ({stance}).\nVERIFIED CLAIMS:\n{listing}")
    out = []
    for s in data.get("sentences", []):
        cids = [i for i in s.get("claim_ids", []) if i in ids]
        if not cids or len(cids) != len(s.get("claim_ids", [])):
            return None  # the judge cited something that did not survive -> discard and use the template
        cites = sorted({i for cid in cids for i in ids[cid]["cited_chunk_ids"]})
        out.append({"text": s["text"], "citations": cites, "claim_id": ",".join(cids)})
    return out or None
