import os

import pytest

os.environ["SENTARI_SKIP_DOTENV"] = "1"    # tests must never pick up a developer's local .env
os.environ["SENTARI_LLM"] = "heuristic"   # never call an external LLM in tests
os.environ["SENTARI_MODEL"] = "lm_directional"  # never depend on a locally trained/registry model
os.environ.pop("SENTARI_NLI", None)


@pytest.fixture()
def session():
    from storage.db import get_engine, init_db, make_session_factory
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    s = make_session_factory(engine)()
    yield s
    s.close()


@pytest.fixture()
def loaded(session):
    """Sample corpus ingested and scored with the rule-based model."""
    from absa_service.scoring import score_new_chunks
    from absa_service.serving import get_model
    from ingestion.pipeline import ingest
    from ingestion.scrapers.sample import SampleScraper
    ingest(session, ["ACMX", "NVLT"], [SampleScraper()])
    model = get_model("lm_directional")
    score_new_chunks(session, model)
    return session, model
