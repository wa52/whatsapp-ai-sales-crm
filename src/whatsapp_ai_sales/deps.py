"""FastAPI dependencies wired from app state (composition root)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from .messaging.agent import AutoReplyAgent
from .messaging.ingestion import MessageIngestion
from .rag.knowledge_base import KnowledgeBase


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_agent(request: Request, session: SessionDep) -> AutoReplyAgent:
    return request.app.state.build_agent(session)


AgentDep = Annotated[AutoReplyAgent, Depends(get_agent)]


def get_ingestion(request: Request, session: SessionDep) -> MessageIngestion:
    return MessageIngestion(
        session=session,
        agent=request.app.state.build_agent(session),
        provider=request.app.state.provider,
    )


IngestionDep = Annotated[MessageIngestion, Depends(get_ingestion)]


def get_knowledge_base(request: Request, session: SessionDep) -> KnowledgeBase:
    return KnowledgeBase(
        session,
        embedder=request.app.state.embedder,
        vector_store=request.app.state.vector_store,
        max_chars=request.app.state.chunk_max_chars,
        overlap=request.app.state.chunk_overlap,
    )


kb_dep = Annotated[KnowledgeBase, Depends(get_knowledge_base)]
