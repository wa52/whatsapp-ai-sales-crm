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
from .intent import CustomerIntent, IntentExtractor, merge_intents
from .scoring import score_lead


@dataclass(frozen=True)
class HandlingResult:
    handled: bool
    reply_text: str | None = None


class MessageIngestion:
    """Turns an inbound webhook message into persisted state and an outbound reply.

    A message that was already processed (same provider message id) is skipped.
    When an intent extractor is configured, the message also refreshes the
    customer profile and lead score.
    """

    def __init__(
        self,
        *,
        session: Session,
        agent: AutoReplyAgent,
        provider: WhatsAppProvider,
        intent_extractor: IntentExtractor | None = None,
    ) -> None:
        self.session = session
        self._agent = agent
        self._provider = provider
        self._intent_extractor = intent_extractor

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
        if self._intent_extractor is not None:
            self._update_profile(customer, history)
        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.updated_at = now
        customer.updated_at = now
        self.session.commit()

        return HandlingResult(handled=True, reply_text=reply_text)

    def _update_profile(self, customer: Customer, history: list[Message]) -> None:
        merged = self._accumulate_intent(customer, history)
        customer.interested_product = merged.product
        customer.quantity = merged.quantity
        customer.budget = merged.budget
        customer.purchase_time = merged.purchase_time
        customer.customer_type = merged.customer_type
        inbound_count = sum(1 for m in history if m.role == ROLE_INBOUND)
        lead = score_lead(merged, message_count=inbound_count)
        customer.lead_score = lead.score
        customer.lead_level = lead.level

    def _accumulate_intent(self, customer: Customer, history: list[Message]) -> CustomerIntent:
        """Merge intents across all customer messages so earlier signals persist."""
        merged = CustomerIntent(country=customer.country_code)
        for message in history:
            if message.role != ROLE_INBOUND:
                continue
            intent = self._intent_extractor.extract(message.content, customer)
            merged = merge_intents(merged, intent)
        return merged

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
