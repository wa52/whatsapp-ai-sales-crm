"""Query-time retrieval: embed the question, search vectors, resolve chunks."""

from __future__ import annotations

from collections.abc import Callable

from ..models import KnowledgeChunk
from .embeddings import Embedder
from .vectorstore import VectorStore


class Retriever:
    """Retrieves the most relevant knowledge chunks for a customer question."""

    def __init__(
        self,
        *,
        embedder: Embedder,
        vector_store: VectorStore,
        resolver: Callable[[list[int]], dict[int, KnowledgeChunk]],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._resolver = resolver
        self._top_k = top_k
        self._min_score = min_score

    def retrieve(self, query: str) -> list[KnowledgeChunk]:
        vector = self._embedder.embed(query)
        hits = self._vector_store.search(vector, k=self._top_k)
        hits = [(chunk_id, score) for chunk_id, score in hits if score > self._min_score]
        if not hits:
            return []
        ids = [chunk_id for chunk_id, _ in hits]
        by_id = self._resolver(ids)
        return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]
