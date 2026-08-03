"""Database engine, session helpers, and schema creation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  (register tables)
from .config import settings


def create_engine_for(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs: dict = {"connect_args": connect_args}
    if url == "sqlite://":
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


engine = create_engine_for(settings.database_url)


def init_db(url: str | None = None) -> None:
    engine_for = create_engine_for(url or settings.database_url)
    SQLModel.metadata.create_all(engine_for)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    engine_for = create_engine_for(url or settings.database_url)
    with Session(engine_for) as session:
        yield session
