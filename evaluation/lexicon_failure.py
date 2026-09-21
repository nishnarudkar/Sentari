"""Lexicon failure analysis (project.md 7.2).

Runs every lexicon model (and optionally trained models) over the gold set, and reports:
  * error rate on the *trap* subset (sentences where financial semantics invert general-purpose polarity)
    vs the non-trap subset, per model
  * the concrete sentences each lexicon mis-scores, with predicted vs gold label
Output: artifacts/results/lexicon_failures.json (+ a markdown table on stdout)

    python -m evaluation.lexicon_failure
"""
from __future__ import annotations

import json
from pathlib import Path

from absa_service import data as D
from absa_service.models.lexicon import all_lexicon_models
from absa_service.serving import get_model

OUT = Path("artifacts/results/lexicon_failures.json")


def analyse(models, gold: list[D.Example]) -> dict:
    result: dict = {"n_gold": len(gold), "n_trap": sum(g.trap for g in gold), "models": {}}
    for model in models:
        preds = model.predict([g.item() for g in gold])
        wrong = [(g, p) for g, p in zip(gold, preds) if g.label != p.label]

        def err(subset):
            return sum(1 for g, p in zip(gold, preds) if g in subset and g.label != p.label) / max(1, len(subset))
        trap = [g for g in gold if g.trap]
        clean = [g for g in gold if not g.trap]
        result["models"][model.name] = {
            "error_rate": len(wrong) / len(gold),
            "error_rate_trap": err(trap), "error_rate_nontrap": err(clean),
            "failures": [{"aspect": g.aspect, "sentence": g.text, "gold": g.label, "predicted": p.label,
                          "score": round(p.score, 3), "trap": g.trap} for g, p in wrong],
        }
    return result


def markdown_table(result: dict) -> str:
    lines = ["| model | error (all) | error (trap) | error (non-trap) |", "|---|---|---|---|"]
    for name, m in result["models"].items():
        lines.append(f"| {name} | {m['error_rate']:.1%} | {m['error_rate_trap']:.1%} | {m['error_rate_nontrap']:.1%} |")
    return "\n".join(lines)


def main() -> dict:
    gold = D.load_gold()
    models = list(all_lexicon_models())
    for name in ("nb_tfidf", "cnn", "finbert_ft"):  # include trained models when their artifacts exist
        try:
            models.append(get_model(name))
        except Exception:  # noqa: BLE001
            pass
    result = analyse(models, gold)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(markdown_table(result))
    return result


if __name__ == "__main__":
    main()
