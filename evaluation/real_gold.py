"""A human-labelled gold set built from real earnings-call sentences (the pilot corpus).

    python -m evaluation.real_gold export              # -> data/annotation/sentari_annotation.xlsx (+ hidden key)
    python -m evaluation.real_gold import               # labelled xlsx -> data/gold/real_gold.tsv
    python -m evaluation.real_gold evaluate             # every model + stored pipeline scores vs the labels

Sampling: per aspect, sentences where lm_directional and finbert_ft disagree are over-represented (they are
the informative cases) alongside agreed ones, spread across companies and prepared/Q&A. The annotator never
sees model outputs; those stay in the key file. Like data/gold/gold.tsv, the real gold set is for
EVALUATION ONLY - never train on it.

Annotation files live in data/annotation/ (gitignored: they contain transcript excerpts).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from absa_service.schemas import ASPECTS
from storage.models import AspectScore, Chunk, Document

ROOT = Path(__file__).resolve().parents[1]
ANN_DIR = ROOT / "data" / "annotation"
SHEET = ANN_DIR / "sentari_annotation.xlsx"
KEY = ANN_DIR / "annotation_key_DO_NOT_OPEN_WHILE_LABELLING.csv"
REAL_GOLD = ROOT / "data" / "gold" / "real_gold.tsv"
LABELS = ["positive", "neutral", "negative", "not about aspect"]
MODEL_A, MODEL_B = "lm_directional", "finbert_ft"

ASPECT_HELP = {
    "guidance": "the company's outlook / forecast / targets",
    "margins": "profitability, margins, costs, pricing (falling costs = good)",
    "demand": "customer demand, orders, sales volumes, backlog, retention",
    "litigation": "lawsuits, legal and regulatory matters (less legal risk = good)",
    "management_tone": "how confident vs cautious/uncertain/evasive management sounds",
    "liquidity": "cash, debt, credit lines, covenants (less debt / more cash = good)",
}


def candidates(session: Session) -> list[dict]:
    """Every (chunk, aspect) scored by both models, with both labels."""
    a, b = aliased(AspectScore), aliased(AspectScore)
    q = (select(a.chunk_id, a.aspect, a.polarity, b.polarity, Chunk.text, Chunk.section, Chunk.speaker, Chunk.idx,
                Chunk.document_id, Document.ticker, Document.doc_date)
         .join(b, (a.chunk_id == b.chunk_id) & (a.aspect == b.aspect))
         .join(Chunk, Chunk.id == a.chunk_id).join(Document, Document.id == Chunk.document_id)
         .where(a.model_name == MODEL_A, b.model_name == MODEL_B, Document.doc_type == "transcript"))
    out = []
    for cid, aspect, pa, pb, text, section, speaker, idx, doc_id, ticker, date in session.execute(q):
        if 40 <= len(text) <= 400:
            out.append(dict(chunk_id=cid, aspect=aspect, pred_a=pa, pred_b=pb, text=text, section=section,
                            speaker=speaker, idx=idx, document_id=doc_id, ticker=ticker, date=date.isoformat()))
    return out


def sample(cands: list[dict], per_aspect: int = 50, disagree_share: float = 0.6, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    used: set[int] = set()
    picked: list[dict] = []
    for aspect in ASPECTS:
        pool = [c for c in cands if c["aspect"] == aspect]
        dis = [c for c in pool if c["pred_a"] != c["pred_b"]]
        agr = [c for c in pool if c["pred_a"] == c["pred_b"]]
        n_dis = min(len(dis), round(per_aspect * disagree_share))
        for group, n in ((dis, n_dis), (agr, per_aspect - n_dis)):
            rng.shuffle(group)
            # round-robin over companies so no single ticker dominates an aspect
            by_ticker = defaultdict(list)
            for c in group:
                by_ticker[c["ticker"]].append(c)
            order = sorted(by_ticker)
            taken = 0
            while taken < n and any(by_ticker.values()):
                for t in order:
                    while by_ticker[t] and by_ticker[t][0]["chunk_id"] in used:
                        by_ticker[t].pop(0)
                    if by_ticker[t] and taken < n:
                        c = by_ticker[t].pop(0)
                        used.add(c["chunk_id"])
                        picked.append(c)
                        taken += 1
    rng.shuffle(picked)
    for i, c in enumerate(picked, 1):
        c["item_id"] = f"S{i:03d}"
        c["batch"] = (i - 1) // 50 + 1
    return picked


def add_context(session: Session, items: list[dict]) -> None:
    for it in items:
        rows = {c.idx: c for c in session.scalars(select(Chunk).where(
            Chunk.document_id == it["document_id"], Chunk.idx.in_([it["idx"] - 1, it["idx"] + 1])))}
        it["before"] = rows[it["idx"] - 1].text if it["idx"] - 1 in rows else ""
        it["after"] = rows[it["idx"] + 1].text if it["idx"] + 1 in rows else ""


def write_sheet(items: list[dict], path: Path = SHEET, key: Path = KEY) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Instructions"
    lines = [
        ("How to label", True),
        ("For each row, read the SENTENCE (context before/after is only to help) and decide what it says about the ASPECT, "
         "from an investor's point of view: is it good news, bad news, or neither, for that aspect of the company?", False),
        ("", False),
        ("positive  - good news / favourable for that aspect (e.g. margins expanded, costs fell, demand strong, confident)", False),
        ("negative  - bad news / unfavourable (e.g. margins squeezed, debt rose, demand soft, cautious or evasive)", False),
        ("neutral   - factual or balanced, no clear good/bad implication for that aspect", False),
        ("not about aspect - the sentence is not really about this aspect (the system tagged it wrongly)", False),
        ("", False),
        ("Aspects", True),
        *[(f"{a}: {h}", False) for a, h in ASPECT_HELP.items()],
        ("", False),
        ("Tips", True),
        ("- Think direction, not words: 'costs decreased' is POSITIVE for margins; 'litigation expenses rose' is NEGATIVE.", False),
        ("- Mixed sentence: judge the overall implication for THIS aspect; if genuinely balanced, choose neutral.", False),
        ("- Don't overthink: ~20-30 seconds per row. Use Notes for anything odd.", False),
        ("- Do the batches in order (Batch 1 first). Save the file as it is; don't rename or move columns.", False),
        ("- Model predictions are deliberately hidden. Please don't open the key file until you're done.", False),
    ]
    for r, (text, bold) in enumerate(lines, 1):
        ws.cell(row=r, column=1, value=text).font = Font(bold=bold, size=12 if bold else 11)
    ws.column_dimensions["A"].width = 130

    headers = ["item_id", "company", "date", "section", "speaker", "ASPECT", "context before", "SENTENCE",
               "context after", "LABEL", "notes"]
    widths = [8, 8, 11, 9, 18, 16, 38, 60, 38, 16, 24]
    fill = PatternFill("solid", fgColor="FFF7E6")
    for batch in sorted({it["batch"] for it in items}):
        sh = wb.create_sheet(f"Batch {batch}")
        sh.append(headers)
        for c in sh[1]:
            c.font = Font(bold=True)
        for it in [x for x in items if x["batch"] == batch]:
            sh.append([it["item_id"], it["ticker"], it["date"], it["section"], it["speaker"], it["aspect"],
                       it["before"], it["text"], it["after"], None, None])
        for i, w in enumerate(widths, 1):
            sh.column_dimensions[chr(64 + i)].width = w
        for row in sh.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
            row[9].fill = fill
            row[7].font = Font(bold=True)
        dv = DataValidation(type="list", formula1='"' + ",".join(LABELS) + '"', allow_blank=True)
        sh.add_data_validation(dv)
        dv.add(f"J2:J{sh.max_row}")
        sh.freeze_panes = "B2"
    wb.save(path)
    with key.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["item_id", "batch", "chunk_id", "aspect", "ticker", "date", "section",
                                           MODEL_A, MODEL_B])
        w.writeheader()
        for it in items:
            w.writerow({"item_id": it["item_id"], "batch": it["batch"], "chunk_id": it["chunk_id"],
                        "aspect": it["aspect"], "ticker": it["ticker"], "date": it["date"], "section": it["section"],
                        MODEL_A: it["pred_a"], MODEL_B: it["pred_b"]})


def read_labels(path: Path = SHEET) -> list[dict]:
    """Labelled rows from the workbook (unlabelled rows are skipped)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    out = []
    for ws in wb.worksheets:
        if not ws.title.startswith("Batch"):
            continue
        rows = ws.iter_rows(values_only=True)
        header = [str(h) for h in next(rows)]
        for r in rows:
            row = dict(zip(header, r))
            label = (row.get("LABEL") or "").strip().lower()
            if label:
                if label not in LABELS:
                    raise ValueError(f"{row['item_id']}: unknown label {label!r}")
                out.append({"item_id": row["item_id"], "aspect": row["ASPECT"], "sentence": row["SENTENCE"],
                            "label": label, "ticker": row["company"], "date": row["date"], "section": row["section"],
                            "notes": row.get("notes") or ""})
    return out


def import_labels(sheet: Path = SHEET, key: Path = KEY, out: Path = REAL_GOLD) -> dict:
    labels = read_labels(sheet)
    keyrows = {r["item_id"]: r for r in csv.DictReader(key.open(encoding="utf-8"))}
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = [l for l in labels if l["label"] != "not about aspect"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["aspect", "label", "trap", "sentence", "item_id", "chunk_id", "ticker", "date", "section"])
        for l in kept:
            w.writerow([l["aspect"], l["label"], 0, l["sentence"], l["item_id"], keyrows[l["item_id"]]["chunk_id"],
                        l["ticker"], l["date"], l["section"]])
    wrong = len(labels) - len(kept)
    return {"labelled": len(labels), "kept": len(kept), "not_about_aspect": wrong,
            "aspect_precision": round(len(kept) / len(labels), 3) if labels else None}


def evaluate(gold_path: Path = REAL_GOLD, key: Path = KEY) -> dict:
    """(1) the stored pipeline scores of both models vs human labels; (2) every ladder model re-run on the sentences."""
    from absa_service.schemas import Item
    from absa_service.serving import build_model
    from evaluation.metrics import classification_report

    rows = list(csv.DictReader(gold_path.open(encoding="utf-8"), delimiter="\t"))
    keyrows = {r["item_id"]: r for r in csv.DictReader(key.open(encoding="utf-8"))}
    gold = [r["label"] for r in rows]
    result: dict = {"n": len(rows), "stored_pipeline_scores": {}, "models_on_sentences": {}}
    for m in (MODEL_A, MODEL_B):
        preds = [keyrows[r["item_id"]][m] for r in rows]
        result["stored_pipeline_scores"][m] = classification_report(gold, preds)
    for name in ("vader", "sentiwordnet", "lm_lexicon", "lm_directional", "nb_tfidf", "dt_tfidf", "cnn", "lstm",
                 "finbert_ft"):
        try:
            model = build_model(name)
        except Exception as exc:  # noqa: BLE001 - weights may be missing
            result["models_on_sentences"][name] = {"error": str(exc)[:120]}
            continue
        preds = model.predict([Item(text=r["sentence"], aspect=r["aspect"], sentence=r["sentence"]) for r in rows])
        result["models_on_sentences"][name] = classification_report(gold, [p.label for p in preds])
    return result


def main(argv=None):
    import sentari_env  # noqa: F401
    from storage.db import get_engine, make_session_factory

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "import", "evaluate"])
    ap.add_argument("--per-aspect", type=int, default=50)
    args = ap.parse_args(argv)
    if args.cmd == "export":
        with make_session_factory(get_engine())() as s:
            items = sample(candidates(s), per_aspect=args.per_aspect)
            add_context(s, items)
        write_sheet(items)
        print(f"wrote {len(items)} items in {max(i['batch'] for i in items)} batches -> {SHEET}")
    elif args.cmd == "import":
        print(json.dumps(import_labels(), indent=2))
    else:
        res = evaluate()
        out = ROOT / "artifacts" / "results" / "real_gold_eval.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        for group in ("stored_pipeline_scores", "models_on_sentences"):
            for name, rep in res[group].items():
                if "macro_f1" in rep:
                    print(f"{group:24s} {name:15s} macro-F1 {rep['macro_f1']:.3f}  acc {rep['accuracy']:.3f}")


if __name__ == "__main__":
    main()
