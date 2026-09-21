"""Engine/session helpers. DATABASE_URL defaults to a local SQLite file."""
from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base

DEFAULT_URL = "sqlite:///sentari.db"


def get_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", DEFAULT_URL)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, **kwargs)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]):
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
