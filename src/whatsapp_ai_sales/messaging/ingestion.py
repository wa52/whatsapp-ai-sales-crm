"""Inbound message handling: dedupe, persist, and reply end to end."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import phonenumbers
from sqlmodel import Session, select

from ..models import ROLE_INBOUND, ROLE_OUTBOUND, Conversation, Customer, Message, Product
from ..pricing.service import QuoteService, extract_offer
from ..repos import get_conversation_messages
from ..whatsapp.base import WhatsAppProvider
from ..whatsapp.webhook import InboundMessage
from .agent import AutoReplyAgent
from .handling import HANDLER_HUMAN, HandoffSignals, should_handoff
from .intent import CustomerIntent, IntentExtractor, merge_intents
from .notification import KIND_HANDOFF, KIND_LEAD_HIGH, NotificationEvent, Notifier
from .scoring import score_lead


@dataclass(frozen=True)
class HandlingResult:
    handled: bool
    reply_text: str | None = None


@dataclass(frozen=True)
class PricingOutcome:
    text: str
    verdict_action: str | None = None


class MessageIngestion:
    """Turns an inbound webhook message into persisted state and an outbound reply.

    A message that was already processed (same provider message id) is skipped.
    When an intent extractor is configured, the message also refreshes the
    customer profile and lead score; a quote service provides authoritative
    pricing text; a notifier reports handoffs and high-intent leads.
    """

    def __init__(
        self,
        *,
        session: Session,
        agent: AutoReplyAgent,
        provider: WhatsAppProvider,
        intent_extractor: IntentExtractor | None = None,
        quote_service: QuoteService | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.session = session
        self._agent = agent
        self._provider = provider
        self._intent_extractor = intent_extractor
        self._quote_service = quote_service
        self._notifier = notifier

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
        merged: CustomerIntent | None = None
        if self._intent_extractor is not None:
            merged = self._accumulate_intent(customer, history)

        if conversation.handler == HANDLER_HUMAN:
            self._apply_profile_if_needed(customer, merged, history)
            self._touch(customer, conversation)
            self.session.commit()
            return HandlingResult(handled=True, reply_text=None)

        pricing = self._build_pricing(merged, inbound.text)
        reply_text = self._agent.reply(
            history, customer, pricing_text=pricing.text if pricing else None
        )

        signals = HandoffSignals(
            fell_back=reply_text == self._agent.fallback_reply,
            need_human=bool(merged and merged.need_human),
            verdict_human=pricing.verdict_action == "human" if pricing else False,
        )
        handoff = should_handoff(signals)

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
        if merged is not None:
            inbound_count = sum(1 for m in history if m.role == ROLE_INBOUND)
            self._apply_profile(customer, merged, inbound_count)
            if self._notifier is not None and customer.lead_level == "high":
                self._notifier.notify(
                    NotificationEvent(
                        kind=KIND_LEAD_HIGH,
                        wa_id=customer.wa_id,
                        details=f"lead_score={customer.lead_score}",
                    )
                )

        if handoff:
            conversation.handler = HANDLER_HUMAN
            if self._notifier is not None:
                self._notifier.notify(
                    NotificationEvent(
                        kind=KIND_HANDOFF,
                        wa_id=customer.wa_id,
                        details=f"reason=fell_back:{signals.fell_back},"
                        f"need_human:{signals.need_human},verdict_human:{signals.verdict_human}",
                    )
                )

        self._touch(customer, conversation)
        self.session.commit()

        return HandlingResult(handled=True, reply_text=reply_text)

    def _apply_profile_if_needed(
        self, customer: Customer, merged: CustomerIntent | None, history: list[Message]
    ) -> None:
        if merged is None:
            return
        inbound_count = sum(1 for m in history if m.role == ROLE_INBOUND)
        self._apply_profile(customer, merged, inbound_count)

    def _build_pricing(
        self, merged: CustomerIntent | None, current_text: str
    ) -> PricingOutcome | None:
        if merged is None or self._quote_service is None or not merged.product:
            return None
        product = self.session.exec(
            select(Product).where(Product.name == merged.product)
        ).first()
        if product is None:
            return None
        rule = self._quote_service.get_rule(product.id)
        if rule is None:
            return None

        verdict_action: str | None = None
        blocks: list[str] = []
        if merged.need_quote:
            quote = self._quote_service.quote(product, merged.quantity)
            if quote is not None:
                if quote.quantity:
                    blocks.append(
                        f"Authoritative price: {quote.unit_price:.2f} {quote.currency}/unit, "
                        f"total {quote.total_price:.2f} {quote.currency} for "
                        f"{quote.quantity} units. Reply with exactly this; never change "
                        "the numbers."
                    )
                else:
                    blocks.append(
                        f"Authoritative price: {quote.unit_price:.2f} {quote.currency}/unit. "
                        "Reply with exactly this; never change the numbers."
                    )
        offer = extract_offer(current_text)
        if offer is not None:
            verdict = self._quote_service.evaluate_offer(rule, offer)
            verdict_action = verdict.action
            blocks.append(
                f"Customer offered {offer:.2f} {rule.currency}. "
                f"Verdict: {verdict.action}. {verdict.guidance} "
                "Use these figures as-is; never change the numbers."
            )
        if not blocks:
            return None
        return PricingOutcome(text="\n".join(blocks), verdict_action=verdict_action)

    def _apply_profile(
        self, customer: Customer, merged: CustomerIntent, inbound_count: int
    ) -> None:
        customer.interested_product = merged.product
        customer.quantity = merged.quantity
        customer.budget = merged.budget
        customer.purchase_time = merged.purchase_time
        customer.customer_type = merged.customer_type
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

    @staticmethod
    def _touch(customer: Customer, conversation: Conversation) -> None:
        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.updated_at = now
        customer.updated_at = now

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
