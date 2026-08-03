"""Embedding abstraction with a deterministic local implementation."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a fixed-length vector for ``text``."""
        ...


class MockEmbedder:
    """Deterministic n-gram hashing embedder for local dev and tests.

    Produces normalized unit vectors so cosine similarity is meaningful for
    keyword overlap, without any external API. English stopwords are dropped so
    that a question sharing only filler words does not score as a match. Not
    semantically as rich as a real model; swap for a real embedder behind the
    same protocol later.
    """

    def __init__(self, *, dim: int = 1024) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]
        for n in (1, 2):
            for i in range(len(words) - n + 1):
                token = " ".join(words[i : i + n])
                index = _stable_hash(token) % self._dim
                vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "to", "of", "in", "on", "for", "and", "or", "but", "at", "by", "with",
        "what", "how", "when", "where", "which", "who", "do", "does", "did",
        "i", "you", "we", "they", "he", "she", "it", "me", "my", "your", "our",
        "their", "this", "that", "these", "those", "have", "has", "had",
        "would", "will", "can", "could", "should", "there", "here", "not",
        "no", "yes", "please", "about", "into", "from", "as", "up", "down",
        "out", "so", "than", "then", "just", "very",
    }
)


def _stable_hash(text: str) -> int:
    """Process-independent hash so vector similarity is reproducible."""
    digest = hashlib.md5(text.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big")
