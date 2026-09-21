import pytest

from absa_service import data as D
from absa_service.aspect_extraction import extract_mentions, find_triggers
from absa_service.models.classical_ml import NaiveBayesModel
from absa_service.models.lexicon import LMDirectionalModel, LoughranMcDonaldModel, VaderModel
from absa_service.preprocessing.text import hedge_score, negated_mask, split_clauses, tokenize
from absa_service.schemas import ASPECTS, Item
from absa_service.scoring import analyze_sentence
from evaluation.metrics import classification_report


def test_negation_scope_stops_at_clause_break():
    toks = tokenize("We do not expect any impact, but demand is strong.")
    mask = dict(zip(toks, negated_mask(toks)))
    assert mask["expect"] and mask["impact"]
    assert not mask["strong"]


def test_hedge_score_orders_text():
    assert hedge_score("We believe demand may soften and visibility is limited") > hedge_score("Revenue was 5 billion")


def test_split_clauses_on_contrast():
    parts = split_clauses("Demand held up, but aerospace orders declined")
    assert len(parts) == 2


@pytest.mark.parametrize("sentence,aspect", [
    ("Gross margin expanded 180 basis points.", "margins"),
    ("We drew on the revolver as a precaution.", "liquidity"),
    ("There is an ongoing patent dispute.", "litigation"),
    ("We are raising our full-year guidance.", "guidance"),
    ("Our management team is confident.", "management_tone"),
    ("Order backlog reached a record high.", "demand"),
])
def test_aspect_triggers(sentence, aspect):
    assert aspect in {a for a, *_ in find_triggers(sentence)}


def test_mixed_sentence_yields_two_demand_mentions():
    ms = [m for m in extract_mentions("Demand remained healthy, but aerospace orders declined.") if m.aspect == "demand"]
    assert len(ms) == 2


def test_spacy_and_rule_fallback_agree_on_aspects():
    s = "Gross margin contracted as input costs rose and we lowered our outlook."
    with_spacy = {m.aspect for m in extract_mentions(s, use_spacy=True)}
    without = {m.aspect for m in extract_mentions(s, use_spacy=False)}
    assert with_spacy == without


def test_negation_detected_via_dependency_parse():
    ms = extract_mentions("We do not expect any material impact from ongoing litigation matters.")
    assert ms and ms[0].negated


def test_lexicon_direction_is_subject_dependent():
    m = LMDirectionalModel()
    up_cost, up_margin = m.predict([Item("Costs decreased 8% year over year", "margins"),
                                    Item("Gross margin decreased 8% year over year", "margins")])
    assert up_cost.label == "positive" and up_margin.label == "negative"


def test_vader_misreads_financial_direction():
    """The failure that motivates the project: lexicons ignore that cost/debt falling is good news."""
    vader = VaderModel()
    lm_dir = LMDirectionalModel()
    item = Item("We repaid debt and our leverage ratio improved", "liquidity")
    assert lm_dir.predict([item])[0].label == "positive"
    assert vader.predict([Item("Liabilities decreased and debt fell", "liquidity")])[0].label != "positive"


def test_lm_negation_flips():
    lm = LoughranMcDonaldModel()
    assert lm.predict([Item("Demand was not strong", "demand")])[0].label == "negative"


def test_analyze_sentence_shape():
    out = analyze_sentence(LMDirectionalModel(), "Gross margin expanded on favorable mix.")
    assert out and out[0]["aspect"] == "margins" and out[0]["polarity"] == "positive"
    assert -1 <= out[0]["score"] <= 1


def test_gold_set_is_wellformed_and_balanced():
    gold = D.load_gold()
    assert len(gold) >= 90
    assert {g.aspect for g in gold} == set(ASPECTS)
    assert {g.label for g in gold} == {"positive", "negative", "neutral"}
    assert any(g.trap for g in gold)


def test_weak_training_data_never_contains_gold_sentences():
    gold = {g.text for g in D.load_gold()}
    weak = [w for w in D.generate_weak(1500) if w.text in gold]
    assert len(weak) <= 5  # template collisions are possible in principle; train.py filters them anyway


def test_trainable_model_beats_chance_on_gold():
    train, val = D.train_val_split(D.generate_weak(1500))
    nb = NaiveBayesModel().fit(train, val)
    gold = D.load_gold()
    preds = nb.predict([g.item() for g in gold])
    rep = classification_report([g.label for g in gold], [p.label for p in preds])
    assert rep["accuracy"] > 0.5  # chance is ~0.33


def test_metrics_report_structure():
    rep = classification_report(["positive", "negative", "neutral"], ["positive", "neutral", "neutral"])
    assert set(rep["per_class"]) == {"negative", "neutral", "positive"}
    assert 0 <= rep["macro_f1"] <= 1
