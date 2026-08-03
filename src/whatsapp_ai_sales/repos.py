"""Thin data-access helpers shared across the app."""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Message


def get_conversation_messages(session: Session, conversation_id: int) -> list[Message]:
    """All messages of a conversation, oldest first (the canonical ordering)."""
    return session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    ).all()
