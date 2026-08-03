import math

import pytest

from whatsapp_ai_sales.rag.embeddings import MockEmbedder
from whatsapp_ai_sales.rag.vectorstore import MockVectorStore


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def test_mock_embedder_is_deterministic() -> None:
    e = MockEmbedder(dim=64)
    assert e.embed("MOQ is 100 pieces") == e.embed("MOQ is 100 pieces")


def test_mock_embedder_produces_unit_length_vectors() -> None:
    e = MockEmbedder(dim=64)
    vec = e.embed("price list for LED strips")
    assert len(vec) == 64
    assert _norm(vec) == pytest.approx(1.0, abs=1e-6)


def test_mock_embedder_differs_across_texts() -> None:
    e = MockEmbedder(dim=64)
    assert e.embed("hello world") != e.embed("completely different product")


def test_vector_store_search_finds_best_match() -> None:
    store = MockVectorStore()
    e = MockEmbedder()
    store.add(1, e.embed("MOQ is 100 pieces, lead time 15 days"))
    store.add(2, e.embed("sample price is 5 USD"))

    hits = store.search(e.embed("What is the MOQ?"), k=2)

    assert hits[0][0] == 1
    assert hits[0][1] > hits[1][1]


def test_vector_store_search_empty_is_empty() -> None:
    store = MockVectorStore()
    assert store.search([0.1] * 8, k=3) == []


def test_vector_store_delete_removes_vectors() -> None:
    store = MockVectorStore()
    store.add(1, [1.0, 0.0])
    store.add(2, [0.0, 1.0])

    store.delete(1)

    hits = store.search([0.9, 0.1], k=5)
    assert [h[0] for h in hits] == [2]
