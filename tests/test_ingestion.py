from sqlalchemy import func, select

from ingestion.normalize import content_hash, normalize_text, parse_transcript, split_sentences
from ingestion.pipeline import ingest
from ingestion.scrapers.sample import SampleScraper
from storage.db import get_engine, init_db, make_session_factory
from storage.models import Chunk, Document


def make_session():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_normalize_drops_stage_directions_and_fixes_quotes():
    out = normalize_text("Thanks — it’s [Operator Instructions] great.")
    assert "[" not in out and "it's" in out


def test_sentence_split_respects_abbreviations():
    sents = split_sentences("Acme Inc. reported growth. Revenue rose 5%. Margins fell.")
    assert len(sents) == 3
    assert sents[0].startswith("Acme Inc.")


def test_transcript_sections_and_speakers():
    text = (
        "Operator: Welcome to the call.\n"
        "Jane Doe -- CEO: We had a strong quarter. Demand is robust.\n"
        "Operator: We will now begin the question-and-answer session.\n"
        "Bob Lee -- Analyst: Is demand sustainable?\n"
        "Jane Doe -- CEO: We believe so.\n"
    )
    chunks = parse_transcript(text)
    prepared = [c for c in chunks if c.section == "prepared"]
    qa = [c for c in chunks if c.section == "qa"]
    assert any("strong quarter" in c.text for c in prepared)
    assert any("We believe so" in c.text for c in qa)
    assert any(c.speaker.startswith("Jane Doe") for c in prepared)


def test_hash_is_whitespace_and_case_insensitive():
    assert content_hash("Hello  World") == content_hash("hello world")


def test_ingest_is_idempotent():
    session = make_session()
    scrapers = [SampleScraper()]
    first = ingest(session, ["ACMX", "NVLT"], scrapers)
    assert first.new_documents == 5 and first.chunks > 30
    n_docs = session.scalar(select(func.count(Document.id)))
    n_chunks = session.scalar(select(func.count(Chunk.id)))
    second = ingest(session, ["ACMX", "NVLT"], scrapers)
    assert second.new_documents == 0 and second.duplicates == 5
    assert session.scalar(select(func.count(Document.id))) == n_docs
    assert session.scalar(select(func.count(Chunk.id))) == n_chunks


def test_sample_transcript_has_qa_section():
    session = make_session()
    ingest(session, ["ACMX"], [SampleScraper()])
    secs = set(session.scalars(select(Chunk.section)))
    assert {"prepared", "qa", "mdna"} <= secs
