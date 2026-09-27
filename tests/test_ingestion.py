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


def test_sentence_split_handles_ellipsis_only_pieces():
    assert split_sentences("... Well. Revenue grew.") == ["...", "Well.", "Revenue grew."]
    assert split_sentences("...") == ["..."]


def test_one_malformed_document_does_not_abort_ingestion(monkeypatch):
    import datetime as dt
    import ingestion.pipeline as P
    from ingestion.scrapers.base import RawDocument
    session = make_session()

    class Two:
        name = "two"
        def fetch(self, ticker, since=None):
            return [RawDocument(ticker, "news", dt.date(2025, 1, d), f"Bad document number {d} with enough text.")
                    for d in (1, 2)]

    real = P.chunk_document
    monkeypatch.setattr(P, "chunk_document", lambda doc: (_ for _ in ()).throw(ValueError("boom"))
                        if doc.doc_date.day == 1 else real(doc))
    stats = P.ingest(session, ["ZZZ"], [Two()])
    assert stats.new_documents == 1 and len(stats.failures) == 1 and "boom" in stats.failures[0]


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
