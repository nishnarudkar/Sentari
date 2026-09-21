"""Command-line entry points.

    python -m absa_service.cli daily                 # ingest -> score -> briefs -> drift -> digest
    python -m absa_service.cli analyze "Gross margin expanded 180 basis points."
    python -m absa_service.cli brief ACMX            # (re)generate the brief for one ticker
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from sqlalchemy import func, select

from storage.db import get_engine, init_db, make_session_factory
from storage.models import Document


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="sentari")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daily")
    an = sub.add_parser("analyze"); an.add_argument("text"); an.add_argument("--model")
    br = sub.add_parser("brief"); br.add_argument("ticker"); br.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        from absa_service.scoring import analyze_sentence
        from absa_service.serving import get_model
        from ingestion.normalize import split_sentences
        model = get_model(args.model)
        for sent in split_sentences(args.text):
            for r in analyze_sentence(model, sent):
                print(f'[{model.name}] {r["aspect"]:<16} {r["polarity"]:<8} {r["score"]:+.2f}  ({r["trigger"]})  {sent}')
        return

    engine = get_engine()
    init_db(engine)
    with make_session_factory(engine)() as session:
        if args.cmd == "daily":
            from absa_service.orchestration import run_daily
            out = run_daily(session)
            print(json.dumps({k: v for k, v in out.items() if k != "digest"}, indent=2, default=str))
            print(out["digest"]["text"] if out["digest"] else "")
        elif args.cmd == "brief":
            from agents.graph import generate_brief
            t = args.ticker.upper()
            lo, hi = session.execute(select(func.min(Document.doc_date), func.max(Document.doc_date))
                                     .where(Document.ticker == t)).one()
            if lo is None:
                raise SystemExit(f"no documents for {t}; run `daily` first")
            b = generate_brief(session, t, lo, hi, force=args.force)
            print(json.dumps(b.body, indent=2, default=str))


if __name__ == "__main__":
    main()
