"""Transcript-aware preprocessing: tokenization, negation scope, hedge detection.

Negation scope: a negation cue ("not", "no", "without", "n't", "cannot", ...)
flips polarity of tokens until the next clause boundary or `NEG_WINDOW` tokens.
Hedging: management uses modal/epistemic verbs ("may", "could", "believe",
"expect") to soften claims; we normalise these into a hedge score in [0, 1]
that the tone aspect and the model features can use.
"""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*|\d+(?:\.\d+)?%?|[.,;:!?]")

NEGATION_CUES = {
    "not", "no", "never", "without", "cannot", "neither", "nor", "none", "nothing",
    "unable", "hardly", "barely", "n't", "isn't", "aren't", "wasn't", "weren't", "don't",
    "doesn't", "didn't", "won't", "wouldn't", "can't", "couldn't", "shouldn't", "haven't", "hasn't",
    "lack", "lacks", "lacking", "absent",
}
# "no material impact", "not able to say" ... cues followed by these are still negations;
# but "no longer" / "not only" are handled by the window logic staying conservative.
CLAUSE_BREAKS = {",", ";", ":", ".", "!", "?", "but", "although", "though", "however", "while", "whereas", "except"}
NEG_WINDOW = 4

HEDGE_WORDS = {
    "may", "might", "could", "would", "should", "possibly", "perhaps", "potentially", "probably",
    "believe", "believes", "expect", "expects", "anticipate", "anticipates", "hope", "hopefully",
    "approximately", "around", "roughly", "somewhat", "modestly", "limited", "uncertain",
    "uncertainty", "depends", "depending", "subject", "likely", "unlikely", "appear", "appears",
    "suggest", "suggests", "seem", "seems", "difficult", "hard", "unclear", "visibility",
}
CONTRAST_SPLIT = re.compile(r"\s*(?:;|,?\s+\b(?:but|although|though|however|whereas|while|yet)\b)\s*", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def negated_mask(tokens: list[str]) -> list[bool]:
    """mask[i] is True when tokens[i] is inside a negation scope."""
    mask = [False] * len(tokens)
    remaining = 0
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if low in NEGATION_CUES or low.endswith("n't"):
            remaining = NEG_WINDOW
            continue
        if low in CLAUSE_BREAKS:
            remaining = 0
            continue
        if remaining > 0:
            mask[i] = True
            remaining -= 1
    return mask


def hedge_score(text: str) -> float:
    toks = [t.lower() for t in tokenize(text) if t.isalpha() or "'" in t]
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t in HEDGE_WORDS)
    return min(1.0, hits / max(3, len(toks) * 0.25))


def split_clauses(sentence: str) -> list[str]:
    """Split a sentence at contrast conjunctions/semicolons so that
    'Demand held up, but aerospace orders declined' yields two scoreable clauses."""
    parts = [p.strip(" ,") for p in CONTRAST_SPLIT.split(sentence) if p and p.strip(" ,")]
    return parts or [sentence]
