"""LangGraph orchestration: extractor -> (bull || bear) -> skeptic -> judge, plus persistence.

    generate_brief(session, "ACMX", start, end)

Cost control (project.md risks): each brief is fingerprinted by its exact input (ticker + the
chunk ids/scores in the window). If a brief with the same fingerprint exists it is returned without
running the agents, so the LLM is only invoked when new source documents actually arrive.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from absa_service.signals import transcript_delta
from agents import extractor_agent, judge_agent, skeptic_agent
from agents.bull_bear_agents import run_side
from agents.llm import LLM, get_llm
from agents.state import BriefState
from storage.models import AgentTrace, Brief, Document


def build_graph(session: Session, llm: LLM, k: int = 4, model_name: str | None = None):
    """Compile the agent graph. Falls back to a plain sequential runner if langgraph is missing."""
    def extractor_node(state: BriefState) -> dict:
        out = extractor_agent.extract(session, state["ticker"], state["period_start"], state["period_end"],
                                      k=k, model_name=model_name)
        docs = session.scalars(select(Document).where(
            Document.ticker == state["ticker"], Document.doc_type == "transcript",
            Document.doc_date >= state["period_start"], Document.doc_date <= state["period_end"])).all()
        deltas = {d.doc_date.isoformat(): transcript_delta(session, d.id, model_name) for d in docs}
        out["signals"] = {"transcript_deltas": {d: v for d, v in deltas.items() if v is not None}}
        return dict(out)

    def bull_node(state: BriefState) -> dict:
        return run_side("bull", state, llm)

    def bear_node(state: BriefState) -> dict:
        return run_side("bear", state, llm)

    def skeptic_node(state: BriefState) -> dict:
        return skeptic_agent.run(state)

    def judge_node(state: BriefState) -> dict:
        return judge_agent.run(state, llm)

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:  # pragma: no cover
        return _SequentialGraph([extractor_node, bull_node, bear_node, skeptic_node, judge_node])

    g = StateGraph(BriefState)
    for name, fn in (("extractor", extractor_node), ("bull", bull_node), ("bear", bear_node),
                     ("skeptic", skeptic_node), ("judge", judge_node)):
        g.add_node(name, fn)
    g.add_edge(START, "extractor")
    g.add_edge("extractor", "bull")
    g.add_edge("extractor", "bear")
    g.add_edge(["bull", "bear"], "skeptic")   # join: skeptic waits for both cases
    g.add_edge("skeptic", "judge")
    g.add_edge("judge", END)
    return g.compile()


class _SequentialGraph:  # pragma: no cover - only used without langgraph
    def __init__(self, nodes):
        self.nodes = nodes

    def invoke(self, state: dict) -> dict:
        state = dict(state)
        for node in self.nodes:
            update = node(state)
            trace = state.get("trace", []) + update.pop("trace", [])
            state.update(update)
            state["trace"] = trace
        return state


def input_fingerprint(session: Session, ticker: str, start: dt.date, end: dt.date, model_name: str | None) -> str:
    from storage.models import AspectScore
    q = select(AspectScore.chunk_id, AspectScore.aspect, AspectScore.score, AspectScore.model_name).where(
        AspectScore.ticker == ticker, AspectScore.doc_date >= start, AspectScore.doc_date <= end)
    if model_name:
        q = q.where(AspectScore.model_name == model_name)
    rows = sorted((r.chunk_id, r.aspect, round(r.score, 3), r.model_name) for r in session.execute(q))
    return hashlib.sha256(json.dumps([ticker, str(start), str(end), rows]).encode()).hexdigest()


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


def generate_brief(session: Session, ticker: str, start: dt.date, end: dt.date, llm: LLM | None = None,
                   model_name: str | None = None, force: bool = False, k: int = 4) -> Brief:
    llm = llm or get_llm()
    fp = input_fingerprint(session, ticker, start, end, model_name) + f":{llm.name}"
    fp = hashlib.sha256(fp.encode()).hexdigest()
    if not force:
        existing = session.scalars(select(Brief).where(Brief.ticker == ticker, Brief.input_fingerprint == fp)
                                   .order_by(Brief.id.desc())).first()
        if existing is not None:
            return existing

    t0 = time.perf_counter()
    before_in, before_out = llm.usage.tokens_in, llm.usage.tokens_out
    graph = build_graph(session, llm, k=k, model_name=model_name)
    final = graph.invoke({"ticker": ticker, "period_start": start, "period_end": end, "trace": []})
    latency = time.perf_counter() - t0

    body = _jsonable(final["brief"])
    body["llm"] = llm.name
    summary = " ".join(s["text"] for s in body["summary"][:2])
    brief = Brief(ticker=ticker, period_start=start, period_end=end, summary=summary,
                  confidence=body["confidence"], body=body, input_fingerprint=fp,
                  tokens_in=llm.usage.tokens_in - before_in, tokens_out=llm.usage.tokens_out - before_out,
                  latency_s=round(latency, 4))
    session.add(brief)
    session.flush()
    for step, entry in enumerate(final.get("trace", []), 1):
        session.add(AgentTrace(brief_id=brief.id, step=step, agent=entry["agent"], payload=_jsonable(entry)))
    session.commit()
    return brief
