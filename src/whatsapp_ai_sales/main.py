"""FastAPI application entrypoint and composition root."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI
from sqlmodel import SQLModel

from .api import crm, webhook
from .config import Settings
from .config import settings as default_settings
from .db import create_engine_for
from .llm.base import ChatMessage
from .llm.litellm_provider import LiteLLMProvider
from .messaging.agent import AutoReplyAgent
from .whatsapp.base import WhatsAppProvider
from .whatsapp.mock import MockWhatsAppProvider


class ReplyLLM(Protocol):
    def chat(self, messages: list[ChatMessage]) -> str:
        ...


def create_app(
    *,
    db_url: str | None = None,
    llm: ReplyLLM | None = None,
    provider: WhatsAppProvider | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or default_settings
    engine = create_engine_for(db_url or settings.database_url)
    SQLModel.metadata.create_all(engine)

    agent = AutoReplyAgent(
        llm or LiteLLMProvider(model=settings.llm_model, api_key=settings.llm_api_key,
                               base_url=settings.llm_base_url),
        system_prompt=settings.system_prompt,
        fallback_reply=settings.fallback_reply,
        window=settings.reply_window,
    )

    app = FastAPI(title="WhatsApp AI Sales")
    app.state.engine = engine
    app.state.agent = agent
    app.state.provider = provider or MockWhatsAppProvider()
    app.include_router(webhook.router)
    app.include_router(crm.router)
    return app


app = create_app()
