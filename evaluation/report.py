"""Render artifacts/results/*.json into one Markdown report (the model-ladder table and companions).

    python -m evaluation.report        # writes artifacts/results/REPORT.md
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path("artifacts/results")
RUNG = {"vader": "Lexicon", "sentiwordnet": "Lexicon", "lm_lexicon": "Lexicon", "lm_directional": "Lexicon + rules",
        "nb_tfidf": "Classical ML", "dt_tfidf": "Classical ML", "cnn": "Deep learning", "lstm": "Deep learning",
        "finbert_zeroshot": "Transformer (no fine-tune)", "finbert_ft": "Transformer (fine-tuned)"}


def ladder_table(results: dict) -> str:
    rows = [(n, r["gold"]) for n, r in results.items() if not n.startswith("_")]
    header = ("| Rung | Model | Accuracy | Macro-F1 | P/R/F1 neg | P/R/F1 neu | P/R/F1 pos | Trap acc. | ms/item |\n"
              "|---|---|---|---|---|---|---|---|---|")
    lines = [header]
    for name, g in rows:
        pc = g["per_class"]
        prf = lambda c: f'{pc[c]["precision"]:.2f}/{pc[c]["recall"]:.2f}/{pc[c]["f1"]:.2f}'  # noqa: E731
        trap = f'{g["trap_accuracy"]:.2f}' if "trap_accuracy" in g else "-"
        lines.append(f'| {RUNG.get(name, "")} | {name} | {g["accuracy"]:.3f} | {g["macro_f1"]:.3f} | '
                     f'{prf("negative")} | {prf("neutral")} | {prf("positive")} | {trap} | {g["latency_ms_per_item"]:.2f} |')
    return "\n".join(lines)


def main() -> str:
    parts = ["# Sentari evaluation report (auto-generated)\n"]
    ladder = RESULTS / "model_ladder.json"
    if ladder.exists():
        res = json.loads(ladder.read_text(encoding="utf-8"))
        meta = res.get("_meta", {})
        parts += ["## 1. Model ladder (one held-out gold set, every approach)\n", ladder_table(res), "",
                  f'*n_gold={meta.get("n_gold")}, n_train(weak labels)={meta.get("n_train")}. {meta.get("note", "")}*\n']
    fail = RESULTS / "lexicon_failures.json"
    if fail.exists():
        from evaluation.lexicon_failure import markdown_table
        res = json.loads(fail.read_text(encoding="utf-8"))
        parts += ["## 2. Lexicon failure analysis\n", markdown_table(res), ""]
    for fname, title in (("grounding_adversarial_heuristic.json", "3a. Grounding audit - adversarial catch rate (heuristic Skeptic)"),
                         ("grounding_adversarial_nli.json", "3a'. Grounding audit - adversarial catch rate (NLI Skeptic)"),
                         ("grounding_human.json", "3b. Grounding audit - human-annotated sample"),
                         ("signal_validity.json", "4. Signal validity"),
                         ("latency_cost.json", "5. Latency and cost")):
        f = RESULTS / fname
        if f.exists():
            parts += [f"## {title}\n", "```json", f.read_text(encoding="utf-8"), "```", ""]
    out = "\n".join(parts)
    (RESULTS / "REPORT.md").write_text(out, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main())
