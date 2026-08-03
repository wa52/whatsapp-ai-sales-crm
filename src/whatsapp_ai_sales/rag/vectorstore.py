"""Vector store abstraction with an in-memory cosine implementation."""

from __future__ import annotations

import math
from typing import Protocol


class VectorStore(Protocol):
    def add(self, chunk_id: int, vector: list[float]) -> None: ...
    def delete(self, chunk_id: int) -> None: ...
    def clear(self) -> None: ...
    def search(self, vector: list[float], *, k: int) -> list[tuple[int, float]]:
        """Return ``k`` (chunk_id, cosine-similarity) pairs, best first."""
        ...


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class MockVectorStore:
    """In-memory vector store using cosine similarity. Lost on restart; the app
    reindexes from the knowledge chunks on startup."""

    def __init__(self) -> None:
        self._vectors: dict[int, list[float]] = {}

    def add(self, chunk_id: int, vector: list[float]) -> None:
        self._vectors[chunk_id] = vector

    def delete(self, chunk_id: int) -> None:
        self._vectors.pop(chunk_id, None)

    def clear(self) -> None:
        self._vectors.clear()

    def search(self, vector: list[float], *, k: int) -> list[tuple[int, float]]:
        scored = [(cid, _cosine(vector, vec)) for cid, vec in self._vectors.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
