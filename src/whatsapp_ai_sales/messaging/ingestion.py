"""Inbound message handling: dedupe, persist, and reply end to end."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import phonenumbers
from sqlmodel import Session, select

from ..models import ROLE_INBOUND, ROLE_OUTBOUND, Conversation, Customer, Message
from ..repos import get_conversation_messages
from ..whatsapp.base import WhatsAppProvider
from ..whatsapp.webhook import InboundMessage
from .agent import AutoReplyAgent


@dataclass(frozen=True)
class HandlingResult:
    handled: bool
    reply_text: str | None = None


class MessageIngestion:
    """Turns an inbound webhook message into persisted state and an outbound reply.

    A message that was already processed (same provider message id) is skipped.
    """

    def __init__(
        self,
        *,
        session: Session,
        agent: AutoReplyAgent,
        provider: WhatsAppProvider,
    ) -> None:
        self.session = session
        self._agent = agent
        self._provider = provider

    def handle_inbound(self, inbound: InboundMessage) -> HandlingResult:
        existing = self.session.exec(
            select(Message).where(Message.provider_message_id == inbound.message_id)
        ).first()
        if existing is not None:
            return HandlingResult(handled=False)

        customer = self._get_or_create(
            Customer,
            [Customer.wa_id == inbound.wa_id],
            wa_id=inbound.wa_id,
            name=inbound.profile_name,
            country_code=derive_country_code(inbound.wa_id),
        )
        conversation = self._get_or_create(
            Conversation,
            [Conversation.customer_id == customer.id, Conversation.status == "active"],
            customer_id=customer.id,
            status="active",
            handler="ai",
        )

        self.session.add(
            Message(
                conversation_id=conversation.id,
                role=ROLE_INBOUND,
                provider_message_id=inbound.message_id,
                content=inbound.text,
            )
        )
        self.session.flush()

        history = get_conversation_messages(self.session, conversation.id)
        reply_text = self._agent.reply(history, customer)

        provider_message_id = self._provider.send_message(customer.wa_id, reply_text)
        self.session.add(
            Message(
                conversation_id=conversation.id,
                role=ROLE_OUTBOUND,
                provider_message_id=provider_message_id,
                content=reply_text,
                status="sent",
            )
        )
        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.updated_at = now
        customer.updated_at = now
        self.session.commit()

        return HandlingResult(handled=True, reply_text=reply_text)

    def _get_or_create(self, model, conditions: list, **fields):
        obj = self.session.exec(select(model).where(*conditions)).first()
        if obj is None:
            obj = model(**fields)
            self.session.add(obj)
            self.session.flush()
        return obj


def derive_country_code(wa_id: str) -> str | None:
    """ISO country code for an E.164 WhatsApp id (no leading ``+``), if parseable."""
    try:
        parsed = phonenumbers.parse(f"+{wa_id}", None)
    except phonenumbers.NumberParseException:
        return None
    return phonenumbers.region_code_for_number(parsed) or None
