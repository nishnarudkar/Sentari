"""Lexicon-based rung of the ladder.

  * VaderModel            - general-purpose social-media lexicon (the "naive" baseline)
  * SentiWordNetModel     - general-purpose WordNet-derived lexicon
  * LoughranMcDonaldModel - finance-specific word lists, plain counting with negation flips
  * LMDirectionalModel    - LM + financial *directionality* rules ("costs fell" is good,
                            "margin fell" is bad) and per-aspect handling of uncertainty
                            and litigious terms; the strongest rule-based system

All score the aspect *clause* (see aspect_extraction), so this is a fair aspect-level
comparison; only how they read the clause differs.
"""
from __future__ import annotations

import re
from functools import lru_cache

from absa_service.models.base import SentimentModel, prediction_from_score
from absa_service.models.lm_lexicon_data import get_lexicon
from absa_service.preprocessing.text import negated_mask, tokenize
from absa_service.schemas import Item, Prediction


class VaderModel(SentimentModel):
    name = "vader"

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._an = SentimentIntensityAnalyzer()

    def predict(self, items: list[Item]) -> list[Prediction]:
        return [prediction_from_score(self._an.polarity_scores(i.text)["compound"], threshold=0.05, scale=1.0)
                for i in items]


@lru_cache(maxsize=1)
def _swn():
    import nltk
    from nltk.corpus import sentiwordnet as swn, wordnet as wn
    try:
        list(swn.senti_synsets("good"))
    except LookupError:
        nltk.download("sentiwordnet", quiet=True)
        nltk.download("wordnet", quiet=True)
    return swn, wn


class SentiWordNetModel(SentimentModel):
    name = "sentiwordnet"
    _POS = {"n": "n", "v": "v", "a": "a", "r": "r"}

    def __init__(self):
        self._swn, self._wn = _swn()
        self._cache: dict[str, float] = {}

    def _word_score(self, word: str) -> float:
        if word in self._cache:
            return self._cache[word]
        senses = list(self._swn.senti_synsets(word))[:3]
        if not senses:
            score = 0.0
        else:
            weights = [1.0, 0.5, 0.33][: len(senses)]
            score = sum(w * (s.pos_score() - s.neg_score()) for w, s in zip(weights, senses)) / sum(weights)
        self._cache[word] = score
        return score

    def predict(self, items: list[Item]) -> list[Prediction]:
        out = []
        for item in items:
            toks = tokenize(item.text)
            mask = negated_mask(toks)
            total = 0.0
            for tok, neg in zip(toks, mask):
                if not tok.isalpha() or len(tok) < 3:
                    continue
                s = self._word_score(tok.lower())
                total += -s if neg else s
            out.append(prediction_from_score(total / max(1, len(toks)) * 4, threshold=0.05))
        return out


class LoughranMcDonaldModel(SentimentModel):
    name = "lm_lexicon"

    def __init__(self):
        lex = get_lexicon()
        self.pos, self.neg = lex["positive"], lex["negative"]

    def predict(self, items: list[Item]) -> list[Prediction]:
        out = []
        for item in items:
            toks = tokenize(item.text)
            mask = negated_mask(toks)
            pos = neg = 0.0
            for tok, negated in zip(toks, mask):
                low = tok.lower()
                if low in self.pos:
                    neg, pos = (neg + 1, pos) if negated else (neg, pos + 1)
                elif low in self.neg:
                    pos, neg = (pos + 1, neg) if negated else (pos, neg + 1)
            out.append(prediction_from_score((pos - neg) / max(1.0, pos + neg) * min(1.0, (pos + neg) / 2 + 0.2),
                                             threshold=0.05))
        return out


UP_WORDS = {"increase", "increased", "increases", "increasing", "rose", "rise", "rising", "risen", "grew", "grow",
            "growth", "growing", "climbed", "climb", "expanded", "expand", "expansion", "jumped", "higher", "up",
            "surged", "accelerated", "raise", "raised", "raising", "lift", "lifted", "lifting", "lengthened",
            "elevated", "outpacing", "outpaced", "added"}
DOWN_WORDS = {"decrease", "decreased", "decreases", "decreasing", "fell", "fall", "falling", "declined", "decline",
              "declining", "dropped", "drop", "shrank", "contracted", "contract", "lower", "lowered", "lowering",
              "reduced", "reduce", "reducing", "reduction", "down", "slipped", "cut", "cuts", "cutting", "eased",
              "narrowed", "shrinking", "tighter"}
# metrics for which "up" is bad news
BAD_WHEN_UP = re.compile(
    r"\b(costs?|expenses?|expense|debt|leverage|borrowings?|churn|cancellations?|liabilit(?:y|ies)|"
    r"litigation|lawsuits?|legal|tariffs?|inflation|maturities|interest|cycles?|delays?|losses|loss|"
    r"scrutiny|exposure|provisions?|charges?|working capital|days)\b", re.I)
GOOD_WHEN_UP_OVERRIDE = re.compile(r"\b(cash conversion|cash|headroom|availability|liquidity)\b", re.I)
NEGATIVE_EVENTS = re.compile(
    r"\b(named as a defendant|subpoena|adverse (?:outcome|ruling)|material charge|verdict went against|"
    r"unable to (?:say|quantify|provide|predict)|not (?:able|comfortable)|difficult to (?:predict|say)|hard to say|"
    r"no longer expect|failure to comply|drew|fully drew|withdraw\w*)\b", re.I)
POSITIVE_EVENTS = re.compile(
    r"\b(dismissed|favorable settlement|in (?:our|its) favor|closed (?:without|with no)|no findings|"
    r"no debt|undrawn|record (?:high|free cash flow|backlog)|above (?:our|the) (?:prior|top)|"
    r"resolved (?:the|earlier)|below the low end of our prior)\b", re.I)


class LMDirectionalModel(SentimentModel):
    """Loughran-McDonald word lists + financial directionality + aspect-aware handling."""

    name = "lm_directional"

    def __init__(self):
        lex = get_lexicon()
        self.pos, self.neg = lex["positive"], lex["negative"]
        self.unc, self.lit = lex["uncertainty"], lex["litigious"]

    def _score(self, item: Item) -> float:
        text = item.text
        toks = tokenize(text)
        mask = negated_mask(toks)
        bad_up = bool(BAD_WHEN_UP.search(text)) and not GOOD_WHEN_UP_OVERRIDE.search(text.split(" and ")[0])
        if item.aspect in ("litigation",) and re.search(r"\b(legal|litigation) (expense|cost)s?\b", text, re.I):
            bad_up = True
        total = 0.0
        direction_hit = False
        for tok, negated in zip(toks, mask):
            low = tok.lower()
            sign = -1.0 if negated else 1.0
            if low in UP_WORDS:
                total += sign * (-1.0 if bad_up else 1.0)
                direction_hit = True
            elif low in DOWN_WORDS:
                total += sign * (1.0 if bad_up else -1.0)
                direction_hit = True
            elif low in self.pos:
                total += sign * 0.8
            elif low in self.neg:
                total -= sign * 0.8
            elif item.aspect == "management_tone" and low in self.unc:
                total -= sign * 0.6
        # "lowered our cost base / costs fell" style handled above; event phrases add explicit evidence
        if NEGATIVE_EVENTS.search(text):
            total -= 1.0
        if POSITIVE_EVENTS.search(text):
            total += 1.0
        # a bare litigious mention with no evaluative evidence is neutral, not negative
        if item.aspect == "litigation" and not direction_hit and abs(total) < 0.5:
            total = 0.0
        # under negation of an entire risk clause ("do not expect any material impact") -> positive
        if item.aspect == "litigation" and re.search(r"\b(do not|does not|don't|no) (?:expect|anticipate)\b.*\b(impact|charge|effect)", text, re.I):
            total += 1.5
        return max(-1.0, min(1.0, total / 2.0))

    def predict(self, items: list[Item]) -> list[Prediction]:
        return [prediction_from_score(self._score(i), threshold=0.12) for i in items]


def all_lexicon_models() -> list[SentimentModel]:
    models: list[SentimentModel] = [VaderModel()]
    try:
        models.append(SentiWordNetModel())
    except Exception:  # noqa: BLE001 - corpus may be missing offline
        pass
    models += [LoughranMcDonaldModel(), LMDirectionalModel()]
    return models
