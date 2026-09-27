"""Compact Loughran-McDonald-style financial word lists (SEED SUBSET).

The official Loughran-McDonald Master Dictionary (Notre Dame SRAF) has ~86k words
and is free for academic use but must be downloaded separately; place the CSV at
data/lexicons/ (any Loughran-McDonald_MasterDictionary*.csv release; gitignored, not
redistributed) and `load_lm_csv()` will use it instead of this seed. This subset was curated by hand from the categories
LM define (negative / positive / uncertainty / litigious) and is enough to run the
pipeline and the lexicon-failure analysis offline; report numbers against the full
dictionary in the final evaluation.
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

LM_PATH = Path(__file__).resolve().parents[2] / "data" / "lexicons" / "Loughran-McDonald_MasterDictionary.csv"

NEGATIVE = {
    "adverse", "adversely", "against", "impairment", "impaired", "weak", "weaker", "weakness", "weakened", "weaken",
    "loss", "losses", "decline", "declined", "declines", "declining", "deteriorate", "deteriorated", "deterioration",
    "shortfall", "shortfalls", "default", "defaults", "delay", "delayed", "delays", "disappointing", "disappointed",
    "disruption", "disruptions", "failure", "failures", "fail", "failed", "headwind", "headwinds", "inability",
    "unable", "unfavorable", "underperform", "underperformed", "volatile", "volatility", "worsen", "worsened",
    "worse", "concern", "concerned", "concerns", "cut", "cuts", "downturn", "restructuring", "writedown", "writeoff",
    "suffered", "suffer", "severe", "pressure", "pressures", "challenging", "challenges", "difficult", "difficulty",
    "negative", "negatively", "penalty", "penalties", "recall", "shortage", "slowdown", "slowing", "softness",
    "soft", "adversary", "burden", "curtail", "damage", "damages", "deficit", "detriment", "erode", "eroded",
    "erosion", "hurt", "inferior", "lawsuit", "lawsuits", "lower", "lowered", "lowering", "poor", "problem",
    "problems", "reduced", "reduction", "risk", "risks", "slump", "strain", "stress", "subpoena", "tighter",
    "tighten", "unfavorably", "withdraw", "withdrawn", "withdrawing", "withdrawal", "misstatement", "fraud",
    "bankruptcy", "insolvency", "downgrade", "downgraded",
}
POSITIVE = {
    "strong", "stronger", "strength", "strengthen", "strengthened", "record", "improve", "improved", "improvement",
    "improving", "improvements", "gain", "gains", "growth", "grew", "robust", "outperform", "outperformed", "exceed",
    "exceeded", "exceeding", "favorable", "favorably", "beat", "confident", "confidence", "optimistic", "excellent",
    "efficient", "efficiencies", "efficiency", "profitable", "profitability", "opportunity", "opportunities",
    "success", "successful", "successfully", "accelerate", "accelerated", "accelerating", "achieve", "achieved",
    "attractive", "benefit", "benefits", "benefited", "best", "better", "boost", "boosted", "breakthrough",
    "enhance", "enhanced", "encouraged", "encouraging", "excited", "expand", "expanded", "expansion", "highest",
    "leading", "lucrative", "momentum", "pleased", "positive", "positively", "resilient", "resilience", "rebound",
    "solid", "superior", "surpass", "surpassed", "upside", "upgrade", "upgraded", "win", "wins", "won", "healthy",
    "strongest",
}
UNCERTAINTY = {
    "may", "might", "could", "possibly", "perhaps", "uncertain", "uncertainty", "uncertainties", "unclear",
    "approximately", "assume", "assumes", "assumption", "believe", "believes", "depend", "depends", "depending",
    "fluctuate", "fluctuations", "indefinite", "likelihood", "probable", "probably", "risk", "risks", "unknown",
    "unpredictable", "variability", "volatile", "volatility", "visibility", "hard", "difficult", "anticipate",
    "estimate", "estimates", "contingent", "exposure", "hope", "hopefully", "roughly", "somewhat", "unable",
}
LITIGIOUS = {
    "litigation", "lawsuit", "lawsuits", "court", "plaintiff", "defendant", "settlement", "verdict", "appeal",
    "arbitration", "subpoena", "injunction", "infringement", "patent", "patents", "legal", "attorney", "jury",
    "regulator", "regulatory", "investigation", "indictment", "sued", "sue", "trial", "judgment", "class action",
    "dispute", "disputes", "allegation", "allegations", "complaint", "claims",
}


def find_lm_csv() -> Path | None:
    """The official dictionary under data/lexicons/, whichever release it is (e.g. ..._1993-2025.csv)."""
    if LM_PATH.exists():
        return LM_PATH
    found = sorted(LM_PATH.parent.glob("Loughran-McDonald_MasterDictionary*.csv"))
    return found[-1] if found else None


def load_lm_csv(path: Path | None = None) -> dict[str, set[str]] | None:
    """Load the official LM Master Dictionary if present (columns: Word, Negative, Positive, Uncertainty, Litigious).

    A category column holds the year a word was added (e.g. 2009), 0 if never in the category, or a negative
    year (e.g. -2020) if the word was later *removed* from it - removed words must not count."""
    path = path or find_lm_csv()
    if path is None or not path.exists():
        return None
    cats = {"negative": set(), "positive": set(), "uncertainty": set(), "litigious": set()}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            word = row["Word"].lower()
            for cat in cats:
                value = (row.get(cat.capitalize()) or "0").strip()
                if value.isdigit() and int(value) > 0:
                    cats[cat].add(word)
    return cats


@lru_cache(maxsize=1)
def get_lexicon() -> dict[str, set[str]]:
    """Official dictionary when present, otherwise the curated seed subset above (SENTARI_LEXICON=seed forces it)."""
    official = None if os.environ.get("SENTARI_LEXICON") == "seed" else load_lm_csv()
    return official or {"negative": NEGATIVE, "positive": POSITIVE,
                             "uncertainty": UNCERTAINTY, "litigious": LITIGIOUS}


def lexicon_source() -> str:
    path = None if os.environ.get("SENTARI_LEXICON") == "seed" else find_lm_csv()
    return path.name if path else "seed subset"
