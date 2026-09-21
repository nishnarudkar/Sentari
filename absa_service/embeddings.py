"""Chunk embeddings for grounding retrieval.

Default: a deterministic signed feature-hashing embedder over unigrams+bigrams
(no download, no GPU, reproducible in tests). If `sentence-transformers` is installed
and SENTARI_EMBEDDER=st, all-MiniLM-L6-v2 (384-d) is used instead.
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache

import numpy as np

DIM = 384
_WORD = re.compile(r"[a-z0-9%]+")
_STOP = {"the", "a", "an", "of", "and", "to", "in", "on", "for", "is", "are", "was", "were", "we", "our", "that",
         "this", "it", "as", "at", "by", "be", "with", "from", "has", "have", "had"}


def _h(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little")


class HashingEmbedder:
    name = "hashing-384"
    dim = DIM

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            words = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
            feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
            for f in feats:
                h = _h(f)
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out


class StEmbedder:  # pragma: no cover - optional heavy dependency
    name = "all-MiniLM-L6-v2"
    dim = 384

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True), dtype="float32")


@lru_cache(maxsize=1)
def get_embedder():
    if os.environ.get("SENTARI_EMBEDDER") == "st":
        try:
            return StEmbedder()
        except Exception:  # noqa: BLE001
            pass
    return HashingEmbedder()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0
