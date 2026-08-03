"""FastAPI application entrypoint and composition root."""

from __future__ import annotations

from fastapi import FastAPI
from sqlmodel import Session, SQLModel

from .api import crm, kb, webhook
from .config import Settings
from .config import settings as default_settings
from .db import create_engine_for
from .llm.base import LLMProvider
from .llm.litellm_provider import LiteLLMProvider
from .messaging.agent import AutoReplyAgent
from .rag.embeddings import MockEmbedder
from .rag.knowledge_base import KnowledgeBase
from .rag.vectorstore import MockVectorStore
from .whatsapp.base import WhatsAppProvider
from .whatsapp.mock import MockWhatsAppProvider


def create_app(
    *,
    db_url: str | None = None,
    llm: LLMProvider | None = None,
    provider: WhatsAppProvider | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or default_settings
    engine = create_engine_for(db_url or settings.database_url)
    SQLModel.metadata.create_all(engine)

    llm = llm or LiteLLMProvider(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    embedder = MockEmbedder()
    vector_store = MockVectorStore()

    with Session(engine) as session:
        KnowledgeBase(
            session,
            embedder=embedder,
            vector_store=vector_store,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap,
        ).reindex()

    def build_agent(session: Session) -> AutoReplyAgent:
        kb = KnowledgeBase(
            session,
            embedder=embedder,
            vector_store=vector_store,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap,
        )
        return AutoReplyAgent(
            llm,
            system_prompt=settings.system_prompt,
            fallback_reply=settings.fallback_reply,
            window=settings.reply_window,
            retriever=kb.retriever(top_k=settings.rag_top_k),
        )

    app = FastAPI(title="WhatsApp AI Sales")
    app.state.engine = engine
    app.state.provider = provider or MockWhatsAppProvider()
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.chunk_max_chars = settings.chunk_max_chars
    app.state.chunk_overlap = settings.chunk_overlap
    app.state.build_agent = build_agent
    app.include_router(webhook.router)
    app.include_router(crm.router)
    app.include_router(kb.router)
    return app


app = create_app()

