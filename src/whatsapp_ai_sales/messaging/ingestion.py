"""Inbound message handling: dedupe, persist, and reply end to end."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from ..models import Conversation, Customer, Message
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

        customer = self._get_or_create_customer(inbound)
        conversation = self._get_or_create_conversation(customer)

        inbound_msg = Message(
            conversation_id=conversation.id,
            role="inbound",
            provider_message_id=inbound.message_id,
            content=inbound.text,
        )
        self.session.add(inbound_msg)
        self.session.flush()

        history = self.session.exec(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        ).all()

        reply_text = self._agent.reply(history, customer)

        provider_message_id = self._provider.send_message(customer.wa_id, reply_text)
        self.session.add(
            Message(
                conversation_id=conversation.id,
                role="outbound",
                provider_message_id=provider_message_id,
                content=reply_text,
                status="sent",
            )
        )
        conversation.last_message_at = datetime.now(UTC)
        conversation.updated_at = datetime.now(UTC)
        customer.updated_at = datetime.now(UTC)
        self.session.commit()

        return HandlingResult(handled=True, reply_text=reply_text)

    def _get_or_create_customer(self, inbound: InboundMessage) -> Customer:
        customer = self.session.exec(
            select(Customer).where(Customer.wa_id == inbound.wa_id)
        ).first()
        if customer is None:
            customer = Customer(wa_id=inbound.wa_id, name=inbound.profile_name)
            self.session.add(customer)
            self.session.flush()
        return customer

    def _get_or_create_conversation(self, customer: Customer) -> Conversation:
        conversation = self.session.exec(
            select(Conversation)
            .where(Conversation.customer_id == customer.id)
            .where(Conversation.status == "active")
        ).first()
        if conversation is None:
            conversation = Conversation(customer_id=customer.id, status="active", handler="ai")
            self.session.add(conversation)
            self.session.flush()
        return conversation
