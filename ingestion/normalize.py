"""Normalize raw text, detect transcript structure, and chunk into sentences.

Transcript conventions handled:
  * Speaker tags at line start:  "Jane Doe -- CFO:"  /  "Operator:"  /  "Jane Doe (CFO): ..."
  * Section switch from prepared remarks to Q&A ("Question-and-Answer Session",
    "Q&A", or the Operator opening the floor to questions).
  * Cross-talk / stage directions in brackets are dropped ("[Operator Instructions]").
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "inc", "corp", "co", "ltd", "vs", "etc", "u.s", "e.g", "i.e",
    "no", "fy", "q1", "q2", "q3", "q4", "approx", "est", "st", "jr", "sr",
}

SPEAKER_RE = re.compile(
    r"^\s*(?P<name>[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})"
    r"(?:\s*(?:--|-|,|\()\s*(?P<role>[A-Za-z&,./ \-]{2,60}?)\)?)?\s*:\s*(?P<rest>.*)$"
)
QA_MARKERS = re.compile(
    r"(question[\s\-]*and[\s\-]*answer|q\s*&\s*a\s+session|open (?:it )?up (?:the line|for questions)|"
    r"first question (?:comes|is) from|we will now begin the question)",
    re.IGNORECASE,
)
STAGE_DIRECTION_RE = re.compile(r"\[[^\]]{0,80}\]|\((?:laughter|inaudible|crosstalk)\)", re.IGNORECASE)
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")


@dataclass
class ChunkDraft:
    idx: int
    text: str
    section: str  # prepared | qa | body
    speaker: str = ""


def normalize_text(raw: str) -> str:
    """Fix encoding artefacts, unify whitespace and quotes, drop stage directions."""
    text = unicodedata.normalize("NFKC", raw)
    text = (text.replace("‘", "'").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "--").replace(" ", " "))
    text = STAGE_DIRECTION_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    canon = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> list[str]:
    """Regex sentence splitter that respects common finance abbreviations."""
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    if not text:
        return []
    pieces = SENT_SPLIT_RE.split(text)
    merged: list[str] = []
    for piece in pieces:
        if merged:
            last_word = merged[-1].rstrip(".").split()[-1].lower().strip("\"'([") if merged[-1].split() else ""
            if merged[-1].endswith(".") and last_word in ABBREVIATIONS:
                merged[-1] = f"{merged[-1]} {piece}"
                continue
        merged.append(piece)
    return [s.strip() for s in merged if len(s.strip()) > 1]


def parse_transcript(text: str) -> list[ChunkDraft]:
    """Split a transcript into sentence chunks tagged with speaker and section."""
    text = normalize_text(text)
    section = "prepared"
    speaker = ""
    chunks: list[ChunkDraft] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        for sent in split_sentences(" ".join(buffer)):
            chunks.append(ChunkDraft(idx=len(chunks), text=sent, section=section, speaker=speaker))
        buffer.clear()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if QA_MARKERS.search(line) and len(line) < 200:
            flush()
            section = "qa"
        m = SPEAKER_RE.match(line)
        if m and len(m.group("name").split()) <= 4 and not line.lower().startswith(("http", "note")):
            flush()
            speaker = m.group("name").strip()
            role = (m.group("role") or "").strip()
            if role:
                speaker = f"{speaker} ({role})"
            line = m.group("rest").strip()
            if speaker.lower().startswith("operator") and QA_MARKERS.search(line):
                section = "qa"
        if line:
            buffer.append(line)
    flush()
    return chunks


def parse_plain(text: str, section: str = "body") -> list[ChunkDraft]:
    """Chunking for filings/news where there is no speaker structure."""
    text = normalize_text(text)
    return [ChunkDraft(idx=i, text=s, section=section) for i, s in enumerate(split_sentences(text))]
