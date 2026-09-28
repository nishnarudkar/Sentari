import datetime as dt

import pytest
from fastapi.testclient import TestClient

from monitoring.drift import compute_drift, psi
from storage.models import AspectScore


def test_psi_zero_for_identical_and_positive_for_shift():
    same = {"guidance": 0.2, "margins": 0.2, "demand": 0.2, "litigation": 0.2, "management_tone": 0.1, "liquidity": 0.1}
    assert psi(same, same) == 0
    shifted = {"guidance": 0.05, "margins": 0.05, "demand": 0.6, "litigation": 0.2, "management_tone": 0.05, "liquidity": 0.05}
    assert psi(shifted, same) > 0.25


def _add_scores(session, chunk_id, ticker, date, aspects, conf):
    for i, a in enumerate(aspects):
        session.add(AspectScore(chunk_id=chunk_id, aspect=a, polarity="neutral", score=0.0, confidence=conf,
                                model_name=f"m{i}{a}", ticker=ticker, doc_date=date))


def test_drift_alerts_on_aspect_mix_shift(loaded):
    session, _ = loaded
    session.query(AspectScore).delete()
    base_day, cur_day = dt.date(2025, 3, 1), dt.date(2025, 3, 30)
    _add_scores(session, 1, "ZZZ", base_day, ["margins", "demand", "guidance", "liquidity"] * 4, 0.7)
    _add_scores(session, 2, "ZZZ", cur_day, ["litigation"] * 12, 0.7)
    session.commit()
    rep = compute_drift(session, "ZZZ", as_of=cur_day)
    assert rep["alert"] and rep["psi_aspect_mix"] > 0.25


def test_run_drift_is_idempotent(loaded):
    from monitoring.drift import run_drift
    from storage.models import DriftReport
    session, _ = loaded
    day = dt.date(2025, 8, 5)
    run_drift(session, ["ACMX", "NVLT"], as_of=day)
    run_drift(session, ["ACMX", "NVLT"], as_of=day)
    assert session.query(DriftReport).count() == 3  # ACMX, NVLT, ALL - not 6


def test_drift_insufficient_data_does_not_alert(session):
    rep = compute_drift(session, "NONE", as_of=dt.date(2025, 1, 1))
    assert rep["status"] == "insufficient_data" and not rep["alert"]


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setenv("SENTARI_LLM", "heuristic")
    from absa_service.main import app
    with TestClient(app) as c:
        yield c


def test_health_and_analyze(client):
    assert client.get("/health").status_code == 200
    r = client.post("/analyze", json={"text": "Gross margin expanded 180 basis points. We are lowering our guidance."})
    assert r.status_code == 200
    got = {(x["aspect"], x["polarity"]) for x in r.json()["results"]}
    assert ("margins", "positive") in got and ("guidance", "negative") in got


def test_score_validates_aspect(client):
    r = client.post("/score", json={"items": [{"text": "x", "aspect": "nonsense"}]})
    assert r.status_code == 422


def test_unknown_model_is_400(client):
    r = client.post("/analyze", json={"text": "Demand is strong.", "model": "nope"})
    assert r.status_code == 400


def test_daily_run_then_dashboard_endpoints(client):
    run = client.post("/run/daily")
    assert run.status_code == 200, run.text
    data = run.json()
    assert data["ingest"]["new_documents"] >= 5 and data["briefs"]
    # idempotent
    again = client.post("/run/daily").json()
    assert again["ingest"]["new_documents"] == 0

    wl = client.get("/watchlist").json()
    assert {t["ticker"] for t in wl["tickers"]} == {"ACMX", "NVLT"}
    traj = client.get("/tickers/ACMX/trajectory").json()
    assert len(traj["aspects"]["margins"]) >= 2

    brief_id = data["briefs"][0]["brief_id"]
    brief = client.get(f"/briefs/{brief_id}").json()
    assert brief["traces"] and brief["sources"]
    cid = next(iter(brief["sources"]))
    chunk = client.get(f"/chunks/{cid}").json()
    assert chunk["chunk"]["text"] and chunk["document"]["title"]
    assert client.get("/digest").json()["moves"]
    assert client.get("/chunks/999999").status_code == 404
    assert "disclaimer" in wl


def test_cron_token_enforced(client, monkeypatch):
    monkeypatch.setenv("SENTARI_CRON_TOKEN", "s3cret")
    assert client.post("/run/daily").status_code == 401
    assert client.post("/run/daily", headers={"X-Cron-Token": "s3cret"}).status_code == 200


def test_digest_compares_same_doc_type_and_needs_enough_mentions(monkeypatch):
    import delivery.digest as D
    traj = [
        {"document_id": 1, "date": "2025-01-01", "doc_type": "transcript", "mean": 0.5, "n": 10},
        {"document_id": 2, "date": "2025-02-01", "doc_type": "transcript", "mean": -0.9, "n": 1},   # too few mentions
        {"document_id": 3, "date": "2025-03-01", "doc_type": "10-Q", "mean": -0.8, "n": 12},        # other doc type
        {"document_id": 4, "date": "2025-04-01", "doc_type": "transcript", "mean": 0.1, "n": 8},
    ]
    monkeypatch.setattr(D, "aspect_trajectory", lambda s, t, a, m=None: traj if a == "demand" else [])
    moves = D.top_moves(None, ["T"])
    assert moves == [{"ticker": "T", "aspect": "demand", "from": 0.5, "to": 0.1, "change": -0.4,
                      "date": "2025-04-01", "document_id": 4}]


def test_brief_window_covers_recent_documents_only(loaded):
    from agents.graph import default_window
    session, _ = loaded
    start, end = default_window(session, "ACMX", days=30)
    assert end == dt.date(2025, 7, 30) and start == dt.date(2025, 6, 30)
    assert default_window(session, "NOPE") is None


def test_quarterly_drift_uses_each_tickers_latest_document(loaded):
    from monitoring.drift import run_drift
    session, _ = loaded
    reps = {r["ticker"]: r for r in run_drift(session, ["ACMX", "NVLT"], as_of=dt.date(2025, 12, 31),
                                              window_days=40, baseline_days=365, min_obs=3)}
    # measured up to each company's own latest call, not the global date (which would leave both windows empty)
    assert reps["ACMX"]["n_current"] > 0 and reps["NVLT"]["n_current"] > 0
