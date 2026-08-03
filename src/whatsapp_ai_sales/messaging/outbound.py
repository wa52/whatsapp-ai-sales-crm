"""Outbound message delivery: retry on transient provider errors, and a re-send
sweep for messages that could not be delivered."""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import ROLE_OUTBOUND, STATUS_FAILED, STATUS_SENT, Conversation, Customer, Message
from ..repos import send_outbound_message, touch
from ..whatsapp.base import WhatsAppProvider


def send_with_retry(
    session: Session,
    provider: WhatsAppProvider,
    conversation: Conversation,
    customer: Customer,
    content: str,
    *,
    max_attempts: int = 3,
) -> Message:
    """Send a message, retrying on transient provider errors before giving up."""
    for attempt in range(1, max_attempts + 1):
        try:
            return send_outbound_message(session, provider, conversation, customer, content)
        except Exception:
            if attempt >= max_attempts:
                raise
    raise RuntimeError("unreachable")


def retry_failed_outbound(
    session: Session,
    provider: WhatsAppProvider,
    *,
    max_attempts: int = 2,
) -> int:
    """Re-send outbound messages marked ``failed``; returns how many were delivered."""
    failed = session.exec(
        select(Message).where(Message.role == ROLE_OUTBOUND, Message.status == STATUS_FAILED)
    ).all()
    resent = 0
    for message in failed:
        if message.attempts >= max_attempts:
            continue
        conversation = session.get(Conversation, message.conversation_id)
        customer = session.get(Customer, conversation.customer_id) if conversation else None
        if conversation is None or customer is None:
            continue
        try:
            provider_message_id = provider.send_message(customer.wa_id, message.content)
            message.provider_message_id = provider_message_id
            message.status = STATUS_SENT
            touch(conversation)
            resent += 1
        except Exception:
            message.attempts += 1
    session.commit()
    return resent
