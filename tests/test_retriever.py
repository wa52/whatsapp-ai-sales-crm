from whatsapp_ai_sales.models import KnowledgeChunk
from whatsapp_ai_sales.rag.embeddings import MockEmbedder
from whatsapp_ai_sales.rag.retriever import Retriever
from whatsapp_ai_sales.rag.vectorstore import MockVectorStore


def _retriever(
    chunks: list[KnowledgeChunk], *, top_k: int = 5
) -> Retriever:
    embedder = MockEmbedder()
    store = MockVectorStore()
    by_id = {c.id: c for c in chunks}
    for chunk in chunks:
        store.add(chunk.id, embedder.embed(chunk.content))
    return Retriever(
        embedder=embedder,
        vector_store=store,
        resolver=lambda ids: {i: by_id[i] for i in ids if i in by_id},
        top_k=top_k,
    )


def test_retriever_returns_most_relevant_first() -> None:
    moq = KnowledgeChunk(
        id=1, product_id=1, section="moq", content="MOQ is 100 pieces, lead time 15 days."
    )
    price = KnowledgeChunk(
        id=2, product_id=1, section="price", content="Sample price is 5 USD."
    )
    retriever = _retriever([moq, price])

    results = retriever.retrieve("What is the MOQ?")

    assert [c.id for c in results] == [1]


def test_retriever_excludes_chunks_sharing_only_stopwords() -> None:
    chunk = KnowledgeChunk(id=1, product_id=1, section="price", content="Sample price is 5 USD.")
    retriever = _retriever([chunk])

    assert retriever.retrieve("What is this thing?") == []


def test_retriever_respects_top_k() -> None:
    chunks = [
        KnowledgeChunk(
            id=i, product_id=1, section="faq", content=f"FAQ about shipping to country {i}."
        )
        for i in range(1, 6)
    ]
    retriever = _retriever(chunks, top_k=3)

    results = retriever.retrieve("shipping to country 4")

    assert len(results) == 3
    assert results[0].id == 4


def test_retriever_empty_when_no_match() -> None:
    chunk = KnowledgeChunk(id=1, product_id=1, section="price", content="Sample price is 5 USD.")
    retriever = _retriever([chunk])

    assert retriever.retrieve("zzz") == []
