"""FastAPI dependencies wired from app state (composition root)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from .messaging.ingestion import MessageIngestion


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_ingestion(request: Request, session: SessionDep) -> MessageIngestion:
    return MessageIngestion(
        session=session,
        agent=request.app.state.agent,
        provider=request.app.state.provider,
    )


IngestionDep = Annotated[MessageIngestion, Depends(get_ingestion)]
