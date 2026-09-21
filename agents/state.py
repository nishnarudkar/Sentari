"""Shared state passed between agents in the LangGraph pipeline."""
from __future__ import annotations

import datetime as dt
import operator
from typing import Annotated, Any, TypedDict


class Evidence(TypedDict):
    chunk_id: int
    aspect: str
    text: str
    score: float
    confidence: float
    section: str
    speaker: str
    doc_id: int
    doc_title: str
    doc_type: str
    doc_date: str
    similarity: float


class Claim(TypedDict, total=False):
    id: str
    side: str                 # bull | bear
    aspect: str
    text: str
    cited_chunk_ids: list[int]
    status: str               # supported | unverified | rejected
    support: dict             # skeptic diagnostics (similarity, entailment, checks)


class BriefState(TypedDict, total=False):
    ticker: str
    period_start: dt.date
    period_end: dt.date
    evidence: list[Evidence]
    aspect_summary: dict[str, dict]
    bull_claims: list[Claim]
    bear_claims: list[Claim]
    verified: list[Claim]
    brief: dict[str, Any]
    signals: dict[str, Any]
    trace: Annotated[list[dict], operator.add]
