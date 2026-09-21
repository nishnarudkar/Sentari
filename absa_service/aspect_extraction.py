"""Aspect extraction: rule-based term matching refined by dependency parsing.

Pipeline per sentence:
  1. split into clauses at contrast conjunctions (so mixed sentences yield separate mentions);
  2. find aspect trigger terms (multi-word aware) in each clause via the ASPECT_TERMS lexicon;
  3. with spaCy available: walk the dependency parse from each trigger to find the
     *opinion words governing it* (amod, the head verb, acomp/attr/xcomp, negations);
     without spaCy: fall back to a +/- 6 token window. Both paths are exercised by tests.
"""
from __future__ import annotations

import re
from functools import lru_cache

from absa_service.preprocessing.text import NEGATION_CUES, hedge_score, split_clauses, tokenize
from absa_service.schemas import ASPECTS, AspectMention

# Trigger terms per aspect. Longest match wins; matching is on lower-cased text.
ASPECT_TERMS: dict[str, list[str]] = {
    "guidance": [
        "guidance", "outlook", "forecast", "full-year", "full year", "annual guidance",
        "we expect revenue", "we expect", "expect revenue", "reiterat", "raising our", "lowering our",
        "maintaining our", "target range", "visibility", "second half", "next few quarters",
    ],
    "margins": [
        "gross margin", "operating margin", "ebitda margin", "net margin", "margin", "margins",
        "profitability", "input cost", "input costs", "cost base", "cost inflation", "pricing",
        "productivity", "operating leverage", "compute costs", "costs", "tariff", "tariffs",
    ],
    "demand": [
        "demand", "orders", "order backlog", "backlog", "bookings", "pipeline", "sales cycle",
        "sales cycles", "deal cycles", "net revenue retention", "net retention", "churn", "retention",
        "revenue", "subscription revenue", "volumes", "customers", "customer",
    ],
    "litigation": [
        "litigation", "lawsuit", "patent", "dispute", "legal", "regulatory", "settlement",
        "investigation", "defendant", "infringement", "material charge", "adverse outcome",
        "class action", "lawsuits", "legal matters",
    ],
    "management_tone": [
        "confident", "confidence", "optimistic", "cautious", "comfortable", "pleased", "concerned",
        "uncertain", "uncertainty", "we believe", "management team", "management is", "monitoring it",
        "difficult to predict", "hard to say", "difficult to say", "not able to say", "unable to",
        "not comfortable", "excited", "disappointed",
    ],
    "liquidity": [
        "liquidity", "cash", "free cash flow", "debt", "revolver", "revolving credit facility",
        "credit facility", "leverage", "covenant", "covenants", "working capital", "balance sheet",
        "cash equivalents", "borrowings", "credit agreement", "leverage ratio",
    ],
}

_CONTRAST_MARKERS = re.compile(r"\b(but|although|though|however|whereas|while|yet)\b", re.I)


@lru_cache(maxsize=1)
def _term_regex() -> list[tuple[str, str, re.Pattern]]:
    entries: list[tuple[str, str, re.Pattern]] = []
    for aspect, terms in ASPECT_TERMS.items():
        for term in sorted(terms, key=len, reverse=True):
            stem = term.endswith(("reiterat",))
            pat = re.compile(rf"\b{re.escape(term)}" + (r"\w*" if stem else r"\b"), re.I)
            entries.append((aspect, term, pat))
    return entries


@lru_cache(maxsize=1)
def _nlp():
    """Load spaCy lazily; returns None if unavailable so the rule fallback is used."""
    try:
        import spacy
        return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    except Exception:  # noqa: BLE001 - spaCy or the model may be absent
        return None


def find_triggers(clause: str) -> list[tuple[str, str, int, int]]:
    """Return (aspect, term, start, end); one hit per aspect (earliest, then longest)."""
    hits: dict[str, tuple[str, int, int]] = {}
    for aspect, term, pat in _term_regex():
        m = pat.search(clause)
        if not m:
            continue
        cur = hits.get(aspect)
        # earliest mention wins (the subject of a clause usually leads); ties -> longest term
        if cur is None or m.start() < cur[1] or (m.start() == cur[1] and m.end() > cur[2]):
            hits[aspect] = (term, m.start(), m.end())
    return [(a, t, s, e) for a, (t, s, e) in hits.items()]


OPINION_POS = {"ADJ", "VERB", "ADV", "NOUN"}
OPINION_DEPS = {"amod", "acomp", "attr", "xcomp", "advmod", "neg", "conj", "advcl", "oprd", "dobj", "npadvmod"}


def _opinion_words_spacy(doc, start: int, end: int) -> tuple[list[str], bool]:
    """Collect words syntactically tied to the aspect span [start, end) (char offsets)."""
    span = doc.char_span(start, end, alignment_mode="expand")
    if span is None:
        return [], False
    words: list[str] = []
    negated = False
    seen: set[int] = set()

    def add(tok):
        if tok.i in seen or tok.is_stop and tok.dep_ != "neg":
            return
        seen.add(tok.i)
        if tok.dep_ == "neg" or tok.lower_ in NEGATION_CUES:
            nonlocal negated
            negated = True
        if tok.pos_ in OPINION_POS and not tok.is_punct and not (start <= tok.idx < end):
            words.append(tok.lower_)

    root = span.root
    for child in root.children:
        if child.dep_ in {"amod", "advmod", "neg", "compound"}:
            add(child)
    head = root.head
    if head is not root:
        add(head)
        for child in head.children:
            if child is not root and child.dep_ in OPINION_DEPS:
                add(child)
                if child.dep_ in {"acomp", "attr", "xcomp", "conj"}:
                    for gc in child.children:
                        if gc.dep_ in {"advmod", "neg", "amod", "prep", "pobj"}:
                            add(gc)
    else:
        for child in root.children:
            if child.dep_ in OPINION_DEPS:
                add(child)
    # walk up a few ancestors: negation/opinion often sits on a governing verb
    # ("we do NOT expect any material impact from ongoing litigation")
    for depth, anc in enumerate(root.ancestors):
        if depth >= 4:
            break
        for child in anc.children:
            if child.dep_ == "neg":
                add(child)
        if anc.pos_ in {"VERB", "ADJ"} and not anc.is_stop:
            add(anc)
    return words, negated


def _opinion_words_window(clause: str, start: int, end: int, window: int = 6) -> tuple[list[str], bool]:
    toks = tokenize(clause)
    trig = set(tokenize(clause[start:end].lower()))
    idxs = [i for i, t in enumerate(toks) if t.lower() in trig]
    if not idxs:
        return [], False
    lo, hi = max(0, min(idxs) - window), min(len(toks), max(idxs) + window + 1)
    ctx = [t.lower() for t in toks[lo:hi] if t.isalpha() and t.lower() not in trig]
    return ctx, any(t in NEGATION_CUES or t.endswith("n't") for t in ctx)


def extract_mentions(sentence: str, use_spacy: bool = True) -> list[AspectMention]:
    """Aspect mentions for one sentence (possibly several clauses x aspects)."""
    mentions: list[AspectMention] = []
    nlp = _nlp() if use_spacy else None
    for clause in split_clauses(sentence):
        triggers = find_triggers(clause)
        if not triggers:
            continue
        doc = nlp(clause) if nlp is not None else None
        for aspect, term, s, e in triggers:
            if doc is not None:
                opinions, negated = _opinion_words_spacy(doc, s, e)
            else:
                opinions, negated = _opinion_words_window(clause, s, e)
            mentions.append(AspectMention(
                aspect=aspect, trigger=clause[s:e], clause=clause, sentence=sentence,
                opinion_words=opinions, negated=negated, hedge=hedge_score(clause),
            ))
    return mentions


def aspects_present(sentence: str) -> list[str]:
    return sorted({m.aspect for m in extract_mentions(sentence, use_spacy=False)}, key=ASPECTS.index)
