"""Grounding audit (project.md 7.3): how well does the Skeptic gate ungrounded claims?

Two complementary measurements:

1. ADVERSARIAL CATCH RATE (automatic). Start from faithful claims (verbatim/near-verbatim from
   scored chunks) and corrupt them in the ways a generator actually fails:
     number_swap      - change a figure ("180 basis points" -> "310 basis points")
     polarity_flip    - reverse the direction ("expanded" -> "contracted", "raising" -> "cutting")
     wrong_citation   - keep the text but cite a chunk about something else
     no_citation      - drop the citation
     fabrication      - a plausible but unsupported claim citing an unrelated chunk
   Reported: catch rate per corruption type (claim not `supported`), and false-rejection rate on the
   faithful claims. NOTE this measures the gate against *synthetic* failures - it is an upper bound on
   real-world catch rate, which is why (2) exists.

2. HUMAN AUDIT (manual). `--export N` samples N claims from persisted briefs into a CSV with an empty
   `human_supported` column (1/0). After annotating, `--score file.csv` reports the fraction of claims that
   are actually supported by their cited source and the Skeptic's agreement with the human label.

    python -m evaluation.grounding_audit --adversarial
    python -m evaluation.grounding_audit --export 50
    python -m evaluation.grounding_audit --score artifacts/results/grounding_audit_sample.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from agents.skeptic_agent import check_claim
from agents.state import Claim, Evidence
from storage.db import get_engine, make_session_factory
from storage.models import AgentTrace, AspectScore, Chunk, Document

OUT_DIR = Path("artifacts/results")
FLIPS = [("expanded", "contracted"), ("improved", "deteriorated"), ("raising", "cutting"), ("raised", "lowered"),
         ("increased", "decreased"), ("grew", "shrank"), ("strong", "weak"), ("record", "declining"),
         ("confident", "concerned"), ("healthy", "deteriorating"), ("lowered", "raised"), ("fell", "rose"),
         ("declined", "increased"), ("contracted", "expanded"), ("lower", "higher"), ("weak", "strong")]
FABRICATIONS = [
    "Management disclosed a pending acquisition that will materially expand the addressable market.",
    "The company announced a large share buyback authorisation funded from operating cash flow.",
    "Management said supply chain disruptions have fully resolved across all regions.",
    "The board approved a significant dividend increase reflecting confidence in cash generation.",
]


def _flip(text: str) -> str | None:
    for a, b in FLIPS:
        if re.search(rf"\b{a}\b", text, re.I):
            return re.sub(rf"\b{a}\b", b, text, count=1, flags=re.I)
    return None


def _swap_number(text: str, rng: random.Random) -> str | None:
    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    val = float(m.group())
    new = val + rng.choice([-1, 1]) * max(1.0, round(val * rng.uniform(0.2, 0.9), 1))
    new_s = f"{new:.1f}" if "." in m.group() else str(int(abs(new)) + 3)
    return text[:m.start()] + new_s + text[m.end():]


def build_cases(evidence: list[Evidence], seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    cases: list[dict] = []
    by_aspect = defaultdict(list)
    for e in evidence:
        by_aspect[e["aspect"]].append(e)
    for e in evidence:
        base = dict(id=f"c{e['chunk_id']}", side="bull" if e["score"] > 0 else "bear", aspect=e["aspect"])
        cases.append({"kind": "faithful", "claim": Claim(**base, text=e["text"], cited_chunk_ids=[e["chunk_id"]])})
        num = _swap_number(e["text"], rng)
        if num:
            cases.append({"kind": "number_swap", "claim": Claim(**base, text=num, cited_chunk_ids=[e["chunk_id"]])})
        flipped = _flip(e["text"])
        if flipped:
            cases.append({"kind": "polarity_flip", "claim": Claim(**base, text=flipped, cited_chunk_ids=[e["chunk_id"]])})
        others = [o for o in evidence if o["aspect"] != e["aspect"]]
        if others:
            o = rng.choice(others)
            cases.append({"kind": "wrong_citation", "claim": Claim(**base, text=e["text"], cited_chunk_ids=[o["chunk_id"]])})
            cases.append({"kind": "fabrication", "claim": Claim(**base, text=rng.choice(FABRICATIONS),
                                                                cited_chunk_ids=[o["chunk_id"]])})
        cases.append({"kind": "no_citation", "claim": Claim(**base, text=e["text"], cited_chunk_ids=[])})
    return cases


def adversarial_audit(evidence: list[Evidence], seed: int = 0) -> dict:
    by_id = {e["chunk_id"]: e for e in evidence}
    stats: dict[str, dict] = defaultdict(lambda: {"n": 0, "supported": 0, "unverified": 0, "rejected": 0})
    for case in build_cases(evidence, seed):
        verdict = check_claim(case["claim"], by_id)["status"]
        s = stats[case["kind"]]
        s["n"] += 1
        s[verdict] += 1
    report = {}
    for kind, s in stats.items():
        if kind == "faithful":
            report[kind] = {**s, "false_rejection_rate": s["rejected"] / s["n"],
                            "false_flag_rate": (s["rejected"] + s["unverified"]) / s["n"]}
        else:
            report[kind] = {**s, "catch_rate": (s["rejected"] + s["unverified"]) / s["n"],
                            "hard_reject_rate": s["rejected"] / s["n"]}
    corrupt = [v for k, v in report.items() if k != "faithful"]
    total = sum(v["n"] for v in corrupt)
    report["_overall"] = {"corrupted_n": total,
                          "overall_catch_rate": sum(v["catch_rate"] * v["n"] for v in corrupt) / max(1, total)}
    return report


def load_evidence(session, limit: int = 400) -> list[Evidence]:
    q = (select(AspectScore, Chunk, Document).join(Chunk, AspectScore.chunk_id == Chunk.id)
         .join(Document, Chunk.document_id == Document.id).where(AspectScore.confidence > 0))
    seen, out = set(), []
    for sc, ch, doc in session.execute(q):
        if ch.id in seen or abs(sc.score) < 0.15 or len(ch.text) < 25:
            continue
        seen.add(ch.id)
        out.append(Evidence(chunk_id=ch.id, aspect=sc.aspect, text=ch.text, score=sc.score,
                            confidence=sc.confidence, section=ch.section, speaker=ch.speaker, doc_id=doc.id,
                            doc_title=doc.title, doc_type=doc.doc_type, doc_date=doc.doc_date.isoformat(), similarity=0.0))
        if len(out) >= limit:
            break
    return out


def export_sample(session, n: int, path: Path, seed: int = 0) -> int:
    rng = random.Random(seed)
    rows = []
    for tr in session.scalars(select(AgentTrace).where(AgentTrace.agent == "skeptic")):
        for c in tr.payload.get("claims", []):
            cited = session.scalars(select(Chunk).where(Chunk.id.in_(c.get("cited_chunk_ids", [])))).all()
            rows.append({"brief_id": tr.brief_id, "claim_id": c["id"], "claim": c["text"],
                         "cited_text": " || ".join(ch.text for ch in cited), "skeptic_status": c["status"],
                         "human_supported": ""})
    rng.shuffle(rows)
    rows = rows[:n]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["brief_id", "claim_id", "claim", "cited_text", "skeptic_status", "human_supported"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def score_human(path: Path) -> dict:
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["human_supported"] in ("0", "1")]
    if not rows:
        raise SystemExit("no annotated rows (fill human_supported with 1/0)")
    supported = [r for r in rows if r["skeptic_status"] == "supported"]
    kept = [r for r in rows if r["skeptic_status"] != "rejected"]
    tp_support = sum(r["human_supported"] == "1" for r in supported)
    unsupported = [r for r in rows if r["human_supported"] == "0"]
    caught = sum(r["skeptic_status"] != "supported" for r in unsupported)
    return {
        "n_annotated": len(rows),
        "human_supported_rate_overall": sum(r["human_supported"] == "1" for r in rows) / len(rows),
        "precision_of_supported": tp_support / len(supported) if supported else None,
        "fraction_of_kept_claims_actually_supported": sum(r["human_supported"] == "1" for r in kept) / len(kept) if kept else None,
        "skeptic_catch_rate_on_unsupported": caught / len(unsupported) if unsupported else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--adversarial", action="store_true")
    ap.add_argument("--export", type=int)
    ap.add_argument("--score", type=Path)
    ap.add_argument("--db", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    factory = make_session_factory(get_engine(args.db))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.adversarial:
        with factory() as s:
            report = adversarial_audit(load_evidence(s), args.seed)
        mode = "nli" if os.environ.get("SENTARI_NLI") == "hf" else "heuristic"
        report["_overall"]["skeptic_entailment_backend"] = mode
        (OUT_DIR / f"grounding_adversarial_{mode}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    if args.export:
        with factory() as s:
            n = export_sample(s, args.export, OUT_DIR / "grounding_audit_sample.csv", args.seed)
        print(f"exported {n} claims -> {OUT_DIR / 'grounding_audit_sample.csv'}")
    if args.score:
        rep = score_human(args.score)
        (OUT_DIR / "grounding_human.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
