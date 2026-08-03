"""Database engine construction."""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine


def create_engine_for(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs: dict = {"connect_args": connect_args}
    if url == "sqlite://":
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)
