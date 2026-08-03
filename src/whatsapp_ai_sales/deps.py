"""FastAPI dependencies wired from app state (composition root)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from .messaging.ingestion import MessageIngestion
from .messaging.intent import IntentExtractor
from .rag.knowledge_base import KnowledgeBase


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_ingestion(request: Request, session: SessionDep) -> MessageIngestion:
    return MessageIngestion(
        session=session,
        agent=request.app.state.build_agent(session),
        provider=request.app.state.provider,
        intent_extractor=IntentExtractor(),
    )


IngestionDep = Annotated[MessageIngestion, Depends(get_ingestion)]


def get_knowledge_base(request: Request, session: SessionDep) -> KnowledgeBase:
    return request.app.state.make_kb(session)


kb_dep = Annotated[KnowledgeBase, Depends(get_knowledge_base)]
