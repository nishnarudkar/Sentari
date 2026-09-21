"""SQLAlchemy schema for Sentari.

Tables (per project.md section 5.4): documents, chunks, aspect_scores, briefs,
agent_traces, model_runs, drift_reports. Works on SQLite (local/dev/tests) and
Postgres (production). Embeddings are stored as JSON arrays so no pgvector is
required for the default path; a pgvector column can be added via migrations.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_documents_content_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    doc_type: Mapped[str] = mapped_column(String(32))  # transcript | 10-K | 10-Q | news | nse_filing
    doc_date: Mapped[dt.date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    source: Mapped[str] = mapped_column(String(128), default="")
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "idx", name="uq_chunks_doc_idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # sentence order within the document
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(32), default="body")  # prepared | qa | mdna | body
    speaker: Mapped[str] = mapped_column(String(128), default="")
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")
    scores: Mapped[list["AspectScore"]] = relationship(back_populates="chunk", cascade="all, delete-orphan")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)  # e.g. lm_lexicon, nb_tfidf, finbert
    version: Mapped[str] = mapped_column(String(64), default="0")
    mlflow_run_id: Mapped[str] = mapped_column(String(64), default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    serving: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AspectScore(Base):
    __tablename__ = "aspect_scores"
    __table_args__ = (
        UniqueConstraint("chunk_id", "aspect", "model_name", name="uq_score_chunk_aspect_model"),
        Index("ix_scores_ticker_aspect_date", "ticker", "aspect", "doc_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"), index=True)
    aspect: Mapped[str] = mapped_column(String(32), index=True)
    polarity: Mapped[str] = mapped_column(String(16))  # positive | negative | neutral
    score: Mapped[float] = mapped_column(Float)  # signed, -1..1
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64), default="0")
    # denormalised for fast time-series queries
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    doc_date: Mapped[dt.date] = mapped_column(Date, index=True)
    section: Mapped[str] = mapped_column(String(32), default="body")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    chunk: Mapped[Chunk] = relationship(back_populates="scores")


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    body: Mapped[dict] = mapped_column(JSON, default=dict)  # structured claims with citations
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    traces: Mapped[list["AgentTrace"]] = relationship(back_populates="brief", cascade="all, delete-orphan")


class AgentTrace(Base):
    """Full audit trail: every agent step of a brief, with cited chunk ids."""

    __tablename__ = "agent_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("briefs.id"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(32))  # extractor | bull | bear | skeptic | judge
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    brief: Mapped[Brief] = relationship(back_populates="traces")


class DriftReport(Base):
    __tablename__ = "drift_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    week_start: Mapped[dt.date] = mapped_column(Date)
    psi_aspect_mix: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_shift: Mapped[float] = mapped_column(Float, default=0.0)
    alert: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
