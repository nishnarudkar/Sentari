import datetime as dt

import pytest

from absa_service import data as D
from absa_service.models.lexicon import LMDirectionalModel, VaderModel
from evaluation import grounding_audit as G
from evaluation.lexicon_failure import analyse, markdown_table
from evaluation.signal_validity import build_events, correlate
from evaluation.latency_cost import report as latency_report
from agents.graph import generate_brief


def test_lexicon_failure_shows_general_lexicon_worse_on_traps():
    res = analyse([VaderModel(), LMDirectionalModel()], D.load_gold())
    v, d = res["models"]["vader"], res["models"]["lm_directional"]
    assert v["error_rate_trap"] > d["error_rate_trap"]
    assert all({"sentence", "gold", "predicted"} <= set(f) for f in v["failures"])
    assert "| vader |" in markdown_table(res)


def test_adversarial_grounding_audit(loaded):
    session, _ = loaded
    ev = G.load_evidence(session)
    assert len(ev) > 10
    rep = G.adversarial_audit(ev)
    assert rep["faithful"]["false_rejection_rate"] <= 0.1          # does not reject honest claims
    assert rep["number_swap"]["catch_rate"] >= 0.9                 # fabricated numbers are caught
    assert rep["no_citation"]["catch_rate"] == 1.0
    assert rep["wrong_citation"]["catch_rate"] >= 0.8
    assert rep["_overall"]["overall_catch_rate"] >= 0.6


def test_export_and_score_human_audit(loaded, tmp_path):
    session, model = loaded
    generate_brief(session, "ACMX", dt.date(2025, 1, 1), dt.date(2025, 12, 31), model_name=model.name)
    path = tmp_path / "sample.csv"
    n = G.export_sample(session, 10, path)
    assert n > 0
    import csv
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        r["human_supported"] = "1" if r["skeptic_status"] == "supported" else "0"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows)
    rep = G.score_human(path)
    assert rep["n_annotated"] == n and rep["precision_of_supported"] == 1.0


def test_signal_validity_pipeline_on_synthetic_returns(loaded):
    """Plumbing check only: returns here are FAKE test data, never a real result."""
    session, model = loaded
    events = build_events(session, model.name)
    assert len(events) == 4 and all(e["delta"] is not None for e in events)
    fake = {(e["ticker"], e["date"]): 0.1 * e["delta"] + 0.001 * i for i, e in enumerate(events)}
    res = correlate(events, fake)
    assert res["n_events"] == 4
    assert "spearman_rho" in res["predictors"]["delta"]
    assert "interpretation" in res


def test_signal_validity_reports_null_for_uncorrelated():
    import random
    rng = random.Random(1)
    events = [{"ticker": "T", "date": dt.date(2020, 1, 1) + dt.timedelta(days=i), "delta": rng.random(),
               "doc_level": rng.random(), "prepared": rng.random()} for i in range(40)]
    rets = {(e["ticker"], e["date"]): rng.gauss(0, 0.03) for e in events}
    res = correlate(events, rets)
    assert res["n_events"] == 40
    assert "null result" in res["interpretation"] or "nominally significant" in res["interpretation"]


def test_latency_cost_report(loaded):
    session, model = loaded
    generate_brief(session, "ACMX", dt.date(2025, 1, 1), dt.date(2025, 12, 31), model_name=model.name)
    rep = latency_report(session)
    assert rep["n_briefs"] == 1 and rep["by_llm"]["heuristic"]["avg_cost_usd_per_brief"] == 0.0
