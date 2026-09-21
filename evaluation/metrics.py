"""Per-class precision/recall/F1 + accuracy, computed the same way for every model."""
from __future__ import annotations

from sklearn.metrics import accuracy_score, precision_recall_fscore_support

from absa_service.schemas import LABELS


def classification_report(y_true: list[str], y_pred: list[str]) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, zero_division=0)
    per_class = {l: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
                 for i, l in enumerate(LABELS)}
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(sum(f) / len(f)),
        "per_class": per_class,
    }


def flat_metrics(report: dict, prefix: str = "") -> dict[str, float]:
    """Flatten a report into MLflow-friendly scalar metrics."""
    out = {f"{prefix}accuracy": report["accuracy"], f"{prefix}macro_f1": report["macro_f1"]}
    for label, m in report["per_class"].items():
        for k in ("precision", "recall", "f1"):
            out[f"{prefix}{label}_{k}"] = m[k]
    return out
