"""Product knowledge base: chunk product fields, embed, and index them."""

from __future__ import annotations

from collections.abc import Callable

from sqlmodel import Session, select

from ..models import KnowledgeChunk, Product
from .chunking import chunk_text
from .embeddings import Embedder
from .retriever import Retriever
from .vectorstore import VectorStore


class KnowledgeBase:
    """Keeps product knowledge in sync between the SQL chunks and the vector store."""

    def __init__(
        self,
        session: Session,
        *,
        embedder: Embedder,
        vector_store: VectorStore,
        max_chars: int = 500,
        overlap: int = 50,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._vector_store = vector_store
        self._max_chars = max_chars
        self._overlap = overlap

    def upsert_product(
        self,
        name: str,
        *,
        sku: str | None = None,
        sections: dict[str, str] | None = None,
    ) -> Product:
        """Create or update a product, rebuilding its chunks and vectors."""
        product = self._session.exec(
            select(Product).where(Product.name == name)
        ).first()
        if product is None:
            product = Product(name=name, sku=sku)
            self._session.add(product)
            self._session.flush()
        else:
            product.sku = sku or product.sku
            self._drop_chunks(product.id)

        for section, text in (sections or {}).items():
            for slice_ in chunk_text(text, max_chars=self._max_chars, overlap=self._overlap):
                chunk = KnowledgeChunk(product_id=product.id, section=section, content=slice_)
                self._session.add(chunk)
                self._session.flush()
                self._vector_store.add(chunk.id, self._embedder.embed(chunk.content))
        self._session.commit()
        return product

    def delete_product(self, product_id: int) -> None:
        product = self._session.get(Product, product_id)
        if product is None:
            return
        self._drop_chunks(product_id)
        self._session.delete(product)
        self._session.commit()

    def list_products(self) -> list[Product]:
        return self._session.exec(select(Product).order_by(Product.id)).all()

    def reindex(self) -> None:
        """Rebuild the vector store from the SQL chunks (e.g. after a restart)."""
        self._vector_store.clear()
        for chunk in self._session.exec(select(KnowledgeChunk)).all():
            self._vector_store.add(chunk.id, self._embedder.embed(chunk.content))

    def retriever(self, top_k: int = 5) -> Retriever:
        return Retriever(
            embedder=self._embedder,
            vector_store=self._vector_store,
            resolver=self._chunk_resolver(),
            top_k=top_k,
        )

    def _drop_chunks(self, product_id: int) -> None:
        chunks = self._session.exec(
            select(KnowledgeChunk).where(KnowledgeChunk.product_id == product_id)
        ).all()
        for chunk in chunks:
            self._vector_store.delete(chunk.id)
            self._session.delete(chunk)

    def _chunk_resolver(self) -> Callable[[list[int]], dict[int, KnowledgeChunk]]:
        session = self._session

        def resolve(chunk_ids: list[int]) -> dict[int, KnowledgeChunk]:
            chunks = session.exec(
                select(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids))
            ).all()
            return {c.id: c for c in chunks}

        return resolve
