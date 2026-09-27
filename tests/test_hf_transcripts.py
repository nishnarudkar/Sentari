import datetime as dt

import pytest

from ingestion.normalize import find_qa_start, parse_segments, speaker_roles
from ingestion.pipeline import ingest, load_config

PREPARED = "Revenue grew and we are raising our full-year guidance. " * 6


def seg(speaker, text):
    return {"speaker": speaker, "text": text}


CALL = [
    seg("Operator", "Welcome. After the prepared remarks there will be a question-and-answer session."),
    seg("Jane Roe", "Thanks. Joining me today is our CFO. " + PREPARED),
    seg("Sam Poe", "Gross margin expanded 120 basis points. " + PREPARED),
    seg("Operator", "Your first question comes from the line of Ann Lee with Big Bank."),
    seg("Ann Lee", "Can you talk about demand in the second half?"),
    seg("Jane Roe", "Demand is uncertain and visibility is limited."),
    seg("Tom Ray", "I would add that pricing may not offset input costs."),
    seg("Operator", "[Operator Instructions]"),
    seg("Bo Wu", "What about the revolver draw?"),
    seg("Sam Poe", "We drew on the revolver as a precaution."),
]


def test_opening_housekeeping_does_not_start_qa():
    assert find_qa_start(CALL) == 3  # not 0, although the opening line mentions the Q&A session


def test_company_handoff_without_operator_intro():
    call = [seg("Jane Roe", PREPARED), seg("Sam Poe", PREPARED + " With that, let's go to Q&A."),
            seg("Ann Lee", "A question on margins?"), seg("Sam Poe", "Margins improved.")]
    assert find_qa_start(call) == 2
    roles = speaker_roles(call, 2)
    assert roles[2] == "Analyst" and roles[3] == ""


def test_no_qa_for_prerecorded_calls():
    assert find_qa_start([seg("Jane Roe", PREPARED), seg("Sam Poe", PREPARED)]) is None


def test_roles_analysts_follow_operator_and_qa_only_executives_are_company():
    roles = speaker_roles(CALL, find_qa_start(CALL))
    assert roles[4] == "Analyst" and roles[8] == "Analyst"   # introduced by the operator
    assert roles[5] == "" and roles[6] == ""                 # CEO, and an executive who only speaks in Q&A
    assert roles[0] == "Operator"


def test_parse_segments_sections_and_speakers():
    chunks = parse_segments(CALL)
    by_speaker = {c.speaker for c in chunks}
    assert "Ann Lee (Analyst)" in by_speaker and "Tom Ray" in by_speaker
    assert {c.section for c in chunks if c.speaker == "Sam Poe"} == {"prepared", "qa"}
    assert all(c.section == "prepared" for c in chunks if "Operator" not in c.speaker and c.idx < 5)
    assert [c.idx for c in chunks] == list(range(len(chunks)))


@pytest.fixture()
def subset(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "subset.parquet"
    con = duckdb.connect()
    con.execute("CREATE TABLE t (symbol VARCHAR, company_name VARCHAR, year BIGINT, quarter BIGINT, date VARCHAR,"
                " structured_content STRUCT(speaker VARCHAR, \"text\" VARCHAR)[])")
    con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", ["ZZZ", "Zed Corp", 2024, 1, "2024-04-25 17:00:00", CALL])
    con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", ["ZZZ", "Zed Corp", 2014, 1, "2014-04-25 17:00:00", CALL[:3]])
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT parquet)")
    return path


def test_scraper_reads_local_subset_and_ingests(subset, session):
    from ingestion.scrapers.hf_transcripts import HfTranscriptScraper
    from storage.models import Chunk
    scraper = HfTranscriptScraper(subset)
    docs = scraper.fetch("ZZZ", since=dt.date(2020, 1, 1))
    assert len(docs) == 1 and docs[0].doc_type == "transcript" and docs[0].title == "Zed Corp Q1 2024 Earnings Call"
    stats = ingest(session, ["ZZZ"], [scraper], since=dt.date(2020, 1, 1))
    assert stats.new_documents == 1
    speakers = {c.speaker for c in session.query(Chunk)}
    assert "Ann Lee (Analyst)" in speakers
    assert ingest(session, ["ZZZ"], [scraper], since=dt.date(2020, 1, 1)).new_documents == 0  # idempotent


def test_extract_rejects_bad_tickers(tmp_path):
    from ingestion.scrapers.hf_transcripts import extract_subset
    with pytest.raises(ValueError):
        extract_subset(["AAPL'; DROP TABLE x; --"], out=tmp_path / "x.parquet")


def test_pilot_config_loads_with_fixed_start_date():
    cfg = load_config("ingestion/pilot_config.yaml")
    assert len(cfg["watchlist"]) == 10 and cfg["sources"] == ["hf_transcripts"]
    assert str(cfg["since"]) == "2015-01-01"
