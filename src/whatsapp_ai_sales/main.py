"""FastAPI application entrypoint and composition root."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, SQLModel

from .api import crm, followup, kb, pricing, reports, telegram, webhook
from .config import Settings
from .config import settings as default_settings
from .db import create_engine_for
from .llm.base import LLMProvider
from .llm.litellm_provider import LiteLLMProvider
from .messaging.agent import AutoReplyAgent
from .messaging.audit import AuditLogger
from .messaging.language import KeywordLanguageDetector
from .messaging.notification import LogNotifier, Notifier
from .rag.embeddings import MockEmbedder
from .rag.knowledge_base import KnowledgeBase
from .rag.vectorstore import MockVectorStore
from .telegram import runtime as telegram_runtime
from .whatsapp.base import WhatsAppProvider
from .whatsapp.mock import MockWhatsAppProvider


def create_app(
    *,
    db_url: str | None = None,
    llm: LLMProvider | None = None,
    provider: WhatsAppProvider | None = None,
    settings: Settings | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    settings = settings or default_settings
    engine = create_engine_for(db_url or settings.database_url)
    SQLModel.metadata.create_all(engine)

    audit = AuditLogger(settings.audit_log_path)
    llm = llm or LiteLLMProvider(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        fallbacks=settings.llm_fallback_models,
        on_usage=lambda usage: audit.log("llm_cost", **usage),
    )
    if provider is None:
        provider = (
            telegram_runtime.TelegramBot(settings.telegram_token)
            if settings.telegram_token
            else MockWhatsAppProvider()
        )
    embedder = MockEmbedder()
    vector_store = MockVectorStore()

    def make_kb(session: Session) -> KnowledgeBase:
        return KnowledgeBase(
            session,
            embedder=embedder,
            vector_store=vector_store,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap,
        )

    def build_agent(session: Session) -> AutoReplyAgent:
        retriever = make_kb(session).retriever(
            top_k=settings.rag_top_k, min_score=settings.rag_min_score
        )
        return AutoReplyAgent(
            llm,
            system_prompt=settings.system_prompt,
            fallback_reply=settings.fallback_reply,
            window=settings.reply_window,
            retriever=retriever,
            language_detector=KeywordLanguageDetector(),
        )

    with Session(engine) as session:
        make_kb(session).reindex()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.settings.followup_scheduler_enabled:
            followup.start_followup_scheduler(app)
        if telegram_runtime.is_telegram_enabled(app):
            telegram_runtime.start_telegram_polling(app)
        try:
            yield
        finally:
            scheduler = getattr(app.state, "scheduler", None)
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="WhatsApp AI Sales", lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = settings
    app.state.llm = llm
    app.state.intent_llm_extract = settings.intent_llm_extract
    app.state.provider = provider or MockWhatsAppProvider()
    app.state.notifier = notifier or LogNotifier()
    app.state.audit = audit
    app.state.make_kb = make_kb
    app.state.build_agent = build_agent
    app.include_router(webhook.router)
    app.include_router(crm.router)
    app.include_router(kb.router)
    app.include_router(pricing.router)
    app.include_router(followup.router)
    app.include_router(reports.router)
    app.include_router(telegram.router)
    admin_dir = Path(__file__).parent / "static" / "admin"
    app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
    return app


app = create_app()
