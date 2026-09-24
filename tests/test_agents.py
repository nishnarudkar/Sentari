import datetime as dt

from sqlalchemy import select

from agents.graph import generate_brief
from agents.llm import HeuristicLLM
from agents.skeptic_agent import check_claim, numbers
from agents.state import Claim, Evidence
from storage.models import AgentTrace, Brief

START, END = dt.date(2025, 1, 1), dt.date(2025, 12, 31)


def ev(cid, text, score=0.8, aspect="margins"):
    return Evidence(chunk_id=cid, aspect=aspect, text=text, score=score, confidence=0.8, section="prepared",
                    speaker="", doc_id=1, doc_title="t", doc_type="transcript", doc_date="2025-04-24", similarity=0.3)


def test_numbers_extraction():
    assert numbers("Revenue grew 12% to 1,200.5 million") == {"12", "1200.5"}


def test_skeptic_supports_faithful_claim():
    e = ev(1, "Gross margin expanded 180 basis points to 34.2% on favorable mix.")
    c = Claim(id="b1", side="bull", aspect="margins", cited_chunk_ids=[1],
              text="Gross margin expanded 180 basis points to 34.2% on favorable mix.")
    assert check_claim(c, {1: e})["status"] == "supported"


def test_skeptic_rejects_fabricated_number():
    e = ev(1, "Gross margin expanded 180 basis points to 34.2% on favorable mix.")
    c = Claim(id="b1", side="bull", aspect="margins", cited_chunk_ids=[1],
              text="Gross margin expanded 300 basis points on favorable mix.")
    out = check_claim(c, {1: e})
    assert out["status"] == "rejected" and "numbers" in out["support"]["reason"]


def test_skeptic_rejects_missing_or_unknown_citation():
    c = Claim(id="b1", side="bull", aspect="margins", cited_chunk_ids=[99], text="Margins expanded.")
    assert check_claim(c, {1: ev(1, "x")})["status"] == "rejected"
    c2 = Claim(id="b2", side="bull", aspect="margins", cited_chunk_ids=[], text="Margins expanded.")
    assert check_claim(c2, {1: ev(1, "x")})["status"] == "rejected"


def test_skeptic_rejects_polarity_contradiction():
    e = ev(1, "Gross margin contracted as costs and tariffs weighed on profitability.", score=-0.9)
    c = Claim(id="b1", side="bull", aspect="margins", cited_chunk_ids=[1],
              text="Gross margin expanded strongly and profitability improved.")
    assert check_claim(c, {1: e})["status"] == "rejected"


def test_skeptic_flags_unrelated_text_as_unverified_or_rejected():
    e = ev(1, "The trial is scheduled to begin in March.", score=0.0, aspect="litigation")
    c = Claim(id="b1", side="bull", aspect="margins", cited_chunk_ids=[1],
              text="Operating discipline and cost programs are lifting the profit outlook materially.")
    assert check_claim(c, {1: e})["status"] in ("unverified", "rejected")


def test_full_graph_produces_grounded_brief(loaded):
    session, model = loaded
    brief = generate_brief(session, "ACMX", START, END, llm=HeuristicLLM(), model_name=model.name)
    body = brief.body
    assert 0 <= brief.confidence <= 1
    assert body["disclaimer"] and body["stance"]
    # every non-header summary sentence must carry citations, and each must resolve to a real chunk
    from storage.models import Chunk
    cited = [c for s in body["summary"] for c in s["citations"]]
    assert cited
    for cid in set(cited):
        assert session.get(Chunk, cid) is not None
    agents = [t.agent for t in session.scalars(select(AgentTrace).where(AgentTrace.brief_id == brief.id))]
    assert {"extractor", "bull", "bear", "skeptic", "judge"} <= set(agents)


def test_brief_is_cached_by_input_fingerprint(loaded):
    session, model = loaded
    llm = HeuristicLLM()
    b1 = generate_brief(session, "NVLT", START, END, llm=llm, model_name=model.name)
    b2 = generate_brief(session, "NVLT", START, END, llm=llm, model_name=model.name)
    assert b1.id == b2.id
    assert len(session.scalars(select(Brief).where(Brief.ticker == "NVLT")).all()) == 1
    b3 = generate_brief(session, "NVLT", START, END, llm=llm, model_name=model.name, force=True)
    assert b3.id != b1.id


def test_one_sentence_is_cited_once_per_side():
    """A sentence that triggers several aspects must not be repeated as several claims."""
    from agents.bull_bear_agents import heuristic_claims
    shared = "Demand conditions are uncertain and we could see additional pressure in the second half."
    evidence = [ev(1, shared, score=-0.95, aspect=a) for a in ("guidance", "demand", "management_tone")]
    evidence[0]["confidence"] = 0.95  # strongest as guidance
    evidence.append(ev(2, "Aerospace orders declined as customers delayed deliveries.", score=-0.7, aspect="demand"))
    claims = heuristic_claims("bear", evidence, max_claims=6)
    cited = [c["cited_chunk_ids"][0] for c in claims]
    assert len(cited) == len(set(cited))
    by_aspect = {c["aspect"]: c["cited_chunk_ids"][0] for c in claims}
    assert by_aspect == {"guidance": 1, "demand": 2}  # tone has no other sentence, so it is left out


def test_judge_merges_duplicate_llm_claims():
    from agents import judge_agent
    from agents.llm import HeuristicLLM
    claim = lambda cid, aspect: Claim(id=cid, side="bear", aspect=aspect, text="x", cited_chunk_ids=[7],  # noqa: E731
                                      status="supported")
    state = {"ticker": "T", "period_start": START, "period_end": END, "evidence": [],
             "aspect_summary": {}, "verified": [claim("br1", "guidance"), claim("br2", "demand")]}
    brief = judge_agent.run(state, HeuristicLLM())["brief"]
    assert sum(len(s["bear"]) for s in brief["sections"].values()) == 1
    assert brief["merged_duplicate_claims"] == 1


def test_briefs_never_repeat_a_sentence_within_a_side(loaded):
    session, model = loaded
    for ticker in ("ACMX", "NVLT"):
        brief = generate_brief(session, ticker, START, END, llm=HeuristicLLM(), model_name=model.name, force=True)
        for side in ("bull", "bear"):
            cited = [c for sect in brief.body["sections"].values() for s in sect[side] for c in s["citations"]]
            assert len(cited) == len(set(cited)), (ticker, side, cited)


def test_rejected_claims_never_reach_the_brief(loaded):
    session, model = loaded
    brief = generate_brief(session, "ACMX", START, END, llm=HeuristicLLM(), model_name=model.name, force=True)
    trace = session.scalars(select(AgentTrace).where(AgentTrace.brief_id == brief.id,
                                                     AgentTrace.agent == "skeptic")).one()
    rejected_ids = {c["id"] for c in trace.payload["claims"] if c["status"] == "rejected"}
    shown = {s["claim_id"] for sect in brief.body["sections"].values() for side in sect.values() for s in side}
    assert not (rejected_ids & shown)
