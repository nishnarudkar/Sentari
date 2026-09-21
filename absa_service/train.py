"""Run the full model ladder: build/train every model, evaluate on the gold set, log to MLflow.

    python -m absa_service.train                       # lexicon + classical + DL
    python -m absa_service.train --transformer         # + fine-tune FinBERT (downloads ~440MB)
    python -m absa_service.train --transformer-zero-shot

Outputs:
    artifacts/models/            trained weights
    artifacts/results/model_ladder.json   one table, one held-out gold set, every approach
    mlruns/                      MLflow tracking store
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from absa_service import data as D
from absa_service.models.classical_ml import DecisionTreeModel, NaiveBayesModel
from absa_service.models.deep_learning import CnnModel, LstmModel
from absa_service.models.lexicon import all_lexicon_models
from absa_service.registry import log_to_mlflow, register_run, set_serving
from evaluation.metrics import classification_report, flat_metrics
from storage.db import get_engine, init_db, make_session_factory, session_scope

log = logging.getLogger("train")
ARTIFACTS = Path("artifacts")


def evaluate(model, examples: list[D.Example]) -> dict:
    t0 = time.perf_counter()
    preds = model.predict([e.item() for e in examples])
    elapsed = time.perf_counter() - t0
    report = classification_report([e.label for e in examples], [p.label for p in preds])
    report["latency_ms_per_item"] = 1000 * elapsed / max(1, len(examples))
    traps = [(e, p) for e, p in zip(examples, preds) if e.trap]
    if traps:
        report["trap_accuracy"] = sum(p.label == e.label for e, p in traps) / len(traps)
        report["trap_n"] = len(traps)
    return report


def build_ladder(args) -> list:
    models = list(all_lexicon_models())
    models += [NaiveBayesModel(), DecisionTreeModel(), CnnModel(epochs=args.epochs), LstmModel(epochs=args.epochs)]
    if args.transformer or args.transformer_zero_shot:
        from absa_service.models.transformer import TransformerModel
        if args.transformer_zero_shot:
            models.append(TransformerModel(name="finbert_zeroshot", zero_shot=True))
        if args.transformer:
            models.append(TransformerModel(name="finbert_ft", epochs=args.tf_epochs, max_train=args.tf_max_train))
    return models


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=4000)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--seeds", type=int, default=1, help="training seeds for trainable models (mean reported)")
    ap.add_argument("--transformer", action="store_true")
    ap.add_argument("--transformer-zero-shot", action="store_true")
    ap.add_argument("--tf-epochs", type=int, default=2)
    ap.add_argument("--tf-max-train", type=int, default=1800)
    ap.add_argument("--db", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    gold = D.load_gold()
    weak = D.generate_weak(args.n_train)
    gold_texts = {g.text for g in gold}
    weak = [w for w in weak if w.text not in gold_texts]  # never train on a test sentence
    train, val = D.train_val_split(weak)
    log.info("train=%d val=%d gold(test)=%d", len(train), len(val), len(gold))

    engine = get_engine(args.db)
    init_db(engine)
    factory = make_session_factory(engine)
    models_dir = ARTIFACTS / "models"
    results: dict[str, dict] = {}

    for model in build_ladder(args):
        log.info("== %s", model.name)
        t0 = time.perf_counter()
        if model.trainable:
            model.fit(train, val)
            model.save(models_dir)
        train_s = time.perf_counter() - t0
        gold_rep = evaluate(model, gold)
        val_rep = evaluate(model, val) if model.trainable else None
        gold_rep["train_seconds"] = train_s
        results[model.name] = {"gold": gold_rep, "val_weak": val_rep,
                               "history": getattr(model, "history", [])}
        log.info("   gold macro-F1=%.3f acc=%.3f trap-acc=%s", gold_rep["macro_f1"], gold_rep["accuracy"],
                 f"{gold_rep.get('trap_accuracy', float('nan')):.3f}")
        metrics = flat_metrics(gold_rep, "gold_")
        metrics.update({"latency_ms": gold_rep["latency_ms_per_item"], "train_seconds": train_s})
        if "trap_accuracy" in gold_rep:
            metrics["gold_trap_accuracy"] = gold_rep["trap_accuracy"]
        run_id = "" if args.no_mlflow else log_to_mlflow(
            model.name, {"rung": type(model).__module__.split(".")[-1], "n_train": len(train)}, metrics,
            str(models_dir) if model.trainable and model.name in ("nb_tfidf", "dt_tfidf") else None)
        with session_scope(factory) as s:
            register_run(s, model.name, {**metrics}, mlflow_run_id=run_id)

    best = max(results, key=lambda n: results[n]["gold"]["macro_f1"])
    with session_scope(factory) as s:
        set_serving(s, best)
    results["_meta"] = {"best": best, "n_train": len(train), "n_gold": len(gold),
                        "note": "Gold set is hand-written; training data are weak template labels. "
                                "lm_directional rules were authored with sight of the gold set -> optimistic."}
    out = ARTIFACTS / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "model_ladder.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    log.info("best on gold: %s -> %s", best, out / "model_ladder.json")
    return results


if __name__ == "__main__":
    main()
