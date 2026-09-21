"""LLM backends for the agent layer.

  * HeuristicLLM  - deterministic, offline, no API key. Agents call `heuristic_*` paths
                    directly; this class exists so the graph runs identically in tests/demo.
  * AnthropicLLM  - Claude via the Anthropic SDK (ANTHROPIC_API_KEY). Token usage is
                    recorded per call so cost per brief can be reported (project.md 7.5).

`get_llm()` returns AnthropicLLM when a key is present and SENTARI_LLM != "heuristic".
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0

    def add(self, i: int, o: int) -> None:
        self.tokens_in += i
        self.tokens_out += o
        self.calls += 1


# USD per million tokens (input, output); used only for the cost report - keep in sync with the provider's price list
PRICE_PER_MTOK = {"claude-sonnet-5": (3.0, 15.0), "claude-haiku-4-5-20251001": (1.0, 5.0)}


@dataclass
class LLM:
    name: str = "base"
    usage: Usage = field(default_factory=Usage)
    is_generative: bool = False

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:  # pragma: no cover
        raise NotImplementedError

    def cost_usd(self) -> float:
        pin, pout = PRICE_PER_MTOK.get(self.name, (0.0, 0.0))
        return (self.usage.tokens_in * pin + self.usage.tokens_out * pout) / 1_000_000


class HeuristicLLM(LLM):
    def __init__(self):
        super().__init__(name="heuristic", is_generative=False)


class AnthropicLLM(LLM):
    def __init__(self, model: str | None = None):
        import anthropic
        super().__init__(name=model or os.environ.get("SENTARI_LLM_MODEL", "claude-sonnet-5"), is_generative=True)
        self.client = anthropic.Anthropic()

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        resp = self.client.messages.create(
            model=self.name, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        self.usage.add(resp.usage.input_tokens, resp.usage.output_tokens)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return parse_json(text)


def parse_json(text: str) -> dict:
    """Extract the first JSON object from a model response (tolerates code fences / prose)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def get_llm() -> LLM:
    if os.environ.get("SENTARI_LLM", "").lower() != "heuristic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicLLM()
        except Exception:  # noqa: BLE001
            pass
    return HeuristicLLM()
