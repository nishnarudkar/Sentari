"""Common interface for every rung of the model ladder."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from pathlib import Path

from absa_service.preprocessing.text import negated_mask, tokenize
from absa_service.schemas import LABEL_TO_SCORE, LABELS, Item, Prediction


class SentimentModel(ABC):
    name = "base"
    version = "0"
    trainable = False

    @abstractmethod
    def predict(self, items: list[Item]) -> list[Prediction]:
        ...

    def fit(self, train, val=None):  # pragma: no cover - only trainable models override
        return self

    def save(self, directory: Path) -> None:  # pragma: no cover
        pass

    def load(self, directory: Path) -> "SentimentModel":  # pragma: no cover
        return self


def prediction_from_probs(probs: dict[str, float]) -> Prediction:
    label = max(probs, key=probs.get)
    score = probs.get("positive", 0.0) - probs.get("negative", 0.0)
    return Prediction(label=label, score=score, confidence=probs[label], probs=probs)


def prediction_from_score(score: float, threshold: float = 0.05, scale: float = 1.0) -> Prediction:
    """Turn a signed lexicon score into a 3-way prediction with a pseudo-confidence."""
    score = max(-1.0, min(1.0, score))
    label = "positive" if score > threshold else "negative" if score < -threshold else "neutral"
    conf = min(1.0, 0.34 + abs(score) * scale * 0.66) if label != "neutral" else max(0.34, 1 - abs(score) * 6)
    probs = {l: 0.0 for l in LABELS}
    probs[label] = conf
    rest = (1 - conf) / 2
    for l in LABELS:
        if l != label:
            probs[l] = rest
    return Prediction(label=label, score=score, confidence=conf, probs=probs)


def marked_tokens(text: str, aspect: str | None = None) -> list[str]:
    """Lower-cased tokens with the classic NEG_ prefix inside negation scope and an aspect token."""
    toks = tokenize(text)
    mask = negated_mask(toks)
    out = [f"NEG_{t.lower()}" if m and t.isalpha() else t.lower() for t, m in zip(toks, mask)]
    return ([f"asp_{aspect}"] if aspect else []) + out


def logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


__all__ = ["SentimentModel", "prediction_from_probs", "prediction_from_score", "marked_tokens",
           "LABELS", "LABEL_TO_SCORE"]
