"""FastAPI dependencies wired from app state (composition root)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlmodel import Session

from .messaging.ingestion import MessageIngestion
from .messaging.intent import IntentExtractor
from .pricing.service import QuoteService
from .rag.knowledge_base import KnowledgeBase
from .whatsapp.base import WhatsAppProvider


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def require_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    """Guard admin APIs when an admin token is configured; webhooks stay public."""
    expected = request.app.state.settings.admin_token
    if expected is not None and x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def get_ingestion(request: Request, session: SessionDep) -> MessageIngestion:
    return build_ingestion(request.app, session)


def build_ingestion(app: FastAPI, session: Session) -> MessageIngestion:
    """Compose the ingestion pipeline from app state (webhook and Telegram both use it)."""
    return MessageIngestion(
        session=session,
        agent=app.state.build_agent(session),
        provider=app.state.provider,
        intent_extractor=_build_intent_extractor(app, session),
        quote_service=QuoteService(session),
        notifier=app.state.notifier,
        audit=app.state.audit,
    )


def get_provider(request: Request) -> WhatsAppProvider:
    return request.app.state.provider


ProviderDep = Annotated[WhatsAppProvider, Depends(get_provider)]


def _build_intent_extractor(app: FastAPI, session: Session) -> IntentExtractor:
    product_keywords = {}
    for product in app.state.make_kb(session).list_products():
        product_keywords[product.name] = product.name.lower().split()
    llm = app.state.llm if app.state.intent_llm_extract else None
    return IntentExtractor(llm, product_keywords=product_keywords)


IngestionDep = Annotated[MessageIngestion, Depends(get_ingestion)]


def get_knowledge_base(request: Request, session: SessionDep) -> KnowledgeBase:
    return request.app.state.make_kb(session)


kb_dep = Annotated[KnowledgeBase, Depends(get_knowledge_base)]
