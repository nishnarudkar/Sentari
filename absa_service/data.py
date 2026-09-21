"""Datasets: hand-annotated gold set (evaluation) + rule-based weak-label generator (training).

The gold set (data/gold/gold.tsv) is small, hand-written, and used ONLY for evaluation.
Training data are template-generated weak labels that encode financial directionality
(e.g. "costs fell" is good, "churn fell" is good, "margin fell" is bad; "improved" is
subject-independent). This mirrors project.md's risk mitigation: a small high-quality
gold set + weak/rule-based labels at scale. Reported numbers must be read with that
caveat: weak-label training is far more homogeneous than real transcripts.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from absa_service.schemas import Item

GOLD_PATH = Path(__file__).resolve().parents[1] / "data" / "gold" / "gold.tsv"


@dataclass
class Example:
    text: str
    aspect: str
    label: str
    trap: bool = False

    def item(self) -> Item:
        return Item(text=self.text, aspect=self.aspect, sentence=self.text)


def load_gold(path: Path = GOLD_PATH) -> list[Example]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = csv.DictReader(fh, delimiter="\t")
        return [Example(r["sentence"].strip(), r["aspect"], r["label"], r["trap"] == "1") for r in rows]


# --------------------------------------------------------------------------- generator
UP = ["increased", "rose", "grew", "climbed", "expanded", "jumped", "went up", "moved higher"]
DOWN = ["decreased", "fell", "declined", "dropped", "shrank", "contracted", "went down", "came down"]
VAL_POS = ["improved", "strengthened", "accelerated", "held up well", "exceeded expectations", "was excellent"]
VAL_NEG = ["deteriorated", "weakened", "worsened", "disappointed", "came under pressure", "was poor"]
NEUTRAL_V = ["was flat", "was unchanged", "was in line with expectations", "was consistent with last quarter",
             "was disclosed in the appendix", "will be discussed later in the call"]
PREFIX = ["", "", "", "During the quarter, ", "Compared with last year, ", "As we noted, ", "In the period, ",
          "Sequentially, ", "For the full year, "]
SUFFIX = ["", "", "", " year over year", " versus the prior quarter", " by {n}%", " to a {adj} level", " in the quarter"]
HEDGE = ["", "", "", "", "We believe ", "We estimate that ", "Management noted that "]

# (subject, good_when_up)
SUBJECTS: dict[str, list[tuple[str, bool]]] = {
    "margins": [("gross margin", True), ("operating margin", True), ("EBITDA margin", True), ("profitability", True),
                ("productivity", True), ("pricing power", True), ("input costs", False), ("cost of revenue", False),
                ("operating expenses", False), ("freight costs", False), ("raw material costs", False),
                ("labor costs", False), ("SG&A expense", False)],
    "demand": [("demand", True), ("order intake", True), ("bookings", True), ("backlog", True), ("the pipeline", True),
               ("customer retention", True), ("unit volumes", True), ("same-store sales", True),
               ("customer churn", False), ("order cancellations", False), ("sales cycles", False),
               ("inventory days at customers", False)],
    "litigation": [("litigation expense", False), ("legal costs", False), ("regulatory scrutiny", False),
                   ("our legal exposure", False), ("settlement costs", False), ("the number of open lawsuits", False)],
    "liquidity": [("cash balance", True), ("free cash flow", True), ("liquidity", True), ("cash conversion", True),
                  ("covenant headroom", True), ("undrawn credit availability", True), ("net debt", False),
                  ("leverage", False), ("borrowings under the revolver", False), ("interest expense", False),
                  ("debt maturities coming due", False)],
}
VALENCE_SUBJECTS = {a: [s for s, _ in subs] for a, subs in SUBJECTS.items()}

GUIDE_NOUN = ["full-year guidance", "annual outlook", "revenue forecast", "margin guidance", "outlook for the second half"]
GUIDE_POS = ["raising", "lifting", "increasing", "upgrading", "narrowing upward"]
GUIDE_NEG = ["lowering", "cutting", "reducing", "withdrawing", "narrowing downward"]
GUIDE_NEU = ["maintaining", "reiterating", "reaffirming", "updating"]

TONE_POS = ["confident", "optimistic", "pleased", "comfortable", "excited", "encouraged"]
TONE_NEG = ["cautious", "concerned", "uncertain", "disappointed", "worried", "not comfortable"]
TONE_TOPIC = ["the outlook", "our execution", "the second half", "the pace of recovery", "our strategy", "the year ahead"]
TONE_NEG_PHRASES = ["It is difficult to predict {t}.", "It is hard to say how {t} will play out.",
                    "We are not able to comment on {t}.", "Visibility on {t} is limited."]
TONE_NEU = ["We will now take questions.", "Please refer to the slides for details on {t}.",
            "We will provide an update on {t} next quarter."]

LIT_POS = ["The court dismissed the case against us.", "We reached a favorable settlement.",
           "The regulatory inquiry was closed with no findings.", "The jury ruled in our favor.",
           "We won the appeal in the patent dispute."]
LIT_NEG = ["We were named as a defendant in a new lawsuit.", "We received a subpoena from the regulator.",
           "An adverse ruling could have a material impact on results.", "The jury verdict went against us.",
           "We recorded a provision for the pending class action."]
LIT_NEU = ["The trial is scheduled for next spring.", "We cannot comment on pending legal proceedings.",
           "Legal proceedings are described in the notes to the financial statements."]


def _decorate(rng: random.Random, core: str) -> str:
    body = core
    suffix = rng.choice(SUFFIX).format(n=rng.choice([2, 3, 5, 7, 9, 12, 15, 20]), adj=rng.choice(["record", "healthy", "low"]))
    text = f"{rng.choice(PREFIX)}{rng.choice(HEDGE)}{body}{suffix}."
    return text[0].upper() + text[1:] if text[:1].islower() else text


def _direction_example(rng: random.Random, aspect: str) -> Example:
    subj, good_up = rng.choice(SUBJECTS[aspect])
    mode = rng.random()
    if mode < 0.40:                                  # direction verb: polarity depends on subject
        up = rng.random() < 0.5
        verb = rng.choice(UP if up else DOWN)
        label = "positive" if (up == good_up) else "negative"
        core = f"{subj} {verb}"
    elif mode < 0.62:                                # valence verb: subject independent
        pos = rng.random() < 0.5
        core = f"{subj} {rng.choice(VAL_POS if pos else VAL_NEG)}"
        label = "positive" if pos else "negative"
    elif mode < 0.78:                                # negated valence
        pos = rng.random() < 0.5
        adj = rng.choice(["strong", "healthy", "solid", "favorable"] if pos else ["weak", "poor", "soft", "unfavorable"])
        core = f"{subj} was not {adj}"
        label = "negative" if pos else "positive"
        if not pos:                                  # "not weak" is only mildly good; keep clear cases only
            core = f"{subj} was not as {adj} as feared"
    elif mode < 0.90:
        core = f"{subj} {rng.choice(NEUTRAL_V)}"
        label = "neutral"
    else:                                            # mixed clause: the aspect verb decides
        up = rng.random() < 0.5
        verb = rng.choice(UP if up else DOWN)
        label = "positive" if (up == good_up) else "negative"
        other = rng.choice(["while the macro backdrop stayed volatile", "in a mixed environment", "despite FX noise"])
        core = f"{subj} {verb} {other}"
    return Example(_decorate(rng, core), aspect, label)


def _guidance_example(rng: random.Random) -> Example:
    r = rng.random()
    noun = rng.choice(GUIDE_NOUN)
    if r < 0.38:
        return Example(_decorate(rng, f"we are {rng.choice(GUIDE_POS)} our {noun}"), "guidance", "positive")
    if r < 0.76:
        return Example(_decorate(rng, f"we are {rng.choice(GUIDE_NEG)} our {noun}"), "guidance", "negative")
    if r < 0.88:
        return Example(_decorate(rng, f"we are {rng.choice(GUIDE_NEU)} our {noun}"), "guidance", "neutral")
    if r < 0.94:
        return Example(_decorate(rng, f"we no longer expect to meet our {noun}"), "guidance", "negative")
    return Example(_decorate(rng, f"we now expect results above our prior {noun}"), "guidance", "positive")


def _tone_example(rng: random.Random) -> Example:
    r, topic = rng.random(), rng.choice(TONE_TOPIC)
    if r < 0.35:
        return Example(_decorate(rng, f"we are {rng.choice(TONE_POS)} about {topic}"), "management_tone", "positive")
    if r < 0.60:
        return Example(_decorate(rng, f"we are {rng.choice(TONE_NEG)} about {topic}"), "management_tone", "negative")
    if r < 0.80:
        return Example(rng.choice(TONE_NEG_PHRASES).format(t=topic), "management_tone", "negative")
    if r < 0.88:
        return Example(_decorate(rng, f"we are not {rng.choice(['confident', 'optimistic', 'comfortable'])} about {topic}"),
                       "management_tone", "negative")
    return Example(rng.choice(TONE_NEU).format(t=topic), "management_tone", "neutral")


def _litigation_example(rng: random.Random) -> Example:
    r = rng.random()
    if r < 0.30:
        return Example(rng.choice(LIT_POS), "litigation", "positive")
    if r < 0.60:
        return Example(rng.choice(LIT_NEG), "litigation", "negative")
    if r < 0.75:
        return Example(rng.choice(LIT_NEU), "litigation", "neutral")
    return _direction_example(rng, "litigation")


def generate_weak(n: int = 4000, seed: int = 13) -> list[Example]:
    """Balanced weak-labelled training set across the six aspects."""
    rng = random.Random(seed)
    makers = {
        "guidance": _guidance_example, "management_tone": _tone_example, "litigation": _litigation_example,
        "margins": lambda r: _direction_example(r, "margins"), "demand": lambda r: _direction_example(r, "demand"),
        "liquidity": lambda r: _direction_example(r, "liquidity"),
    }
    aspects = list(makers)
    out: list[Example] = []
    while len(out) < n:
        aspect = aspects[len(out) % len(aspects)]
        out.append(makers[aspect](rng))
    rng.shuffle(out)
    return out


def train_val_split(examples: list[Example], val_frac: float = 0.15, seed: int = 7):
    rng = random.Random(seed)
    idx = list(range(len(examples)))
    rng.shuffle(idx)
    cut = int(len(idx) * (1 - val_frac))
    return [examples[i] for i in idx[:cut]], [examples[i] for i in idx[cut:]]
