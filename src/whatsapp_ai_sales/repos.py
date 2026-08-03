"""Thin data-access helpers shared across the app."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from .models import ROLE_OUTBOUND, STATUS_SENT, Conversation, Customer, Message
from .whatsapp.base import WhatsAppProvider


def get_conversation_messages(session: Session, conversation_id: int) -> list[Message]:
    """All messages of a conversation, oldest first (the canonical ordering)."""
    return session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    ).all()


def send_outbound_message(
    session: Session,
    provider: WhatsAppProvider,
    conversation: Conversation,
    customer: Customer,
    content: str,
) -> Message:
    """Send a message to the customer via the provider and persist it as outbound."""
    provider_message_id = provider.send_message(customer.wa_id, content)
    message = Message(
        conversation_id=conversation.id,
        role=ROLE_OUTBOUND,
        provider_message_id=provider_message_id,
        content=content,
        status=STATUS_SENT,
    )
    session.add(message)
    return message


def touch(conversation: Conversation, customer: Customer | None = None) -> None:
    """Stamp a conversation (and optionally its customer) as just active."""
    now = datetime.now(UTC)
    conversation.last_message_at = now
    conversation.updated_at = now
    if customer is not None:
        customer.updated_at = now
