"""Shared dataclasses / constants for the ABSA service."""
from __future__ import annotations

from dataclasses import dataclass, field

ASPECTS = ["guidance", "margins", "demand", "litigation", "management_tone", "liquidity"]
LABELS = ["negative", "neutral", "positive"]
LABEL_TO_SCORE = {"negative": -1.0, "neutral": 0.0, "positive": 1.0}


@dataclass
class AspectMention:
    aspect: str
    trigger: str            # the matched aspect term, e.g. "gross margin"
    clause: str             # clause text containing the mention (scored by models)
    sentence: str
    opinion_words: list[str] = field(default_factory=list)
    negated: bool = False
    hedge: float = 0.0


@dataclass
class Item:
    """One unit for a sentiment model: an aspect mention in context."""
    text: str
    aspect: str
    sentence: str = ""
    opinion_words: list[str] = field(default_factory=list)


@dataclass
class Prediction:
    label: str
    score: float             # signed in [-1, 1]
    confidence: float        # [0, 1]
    probs: dict[str, float] = field(default_factory=dict)
