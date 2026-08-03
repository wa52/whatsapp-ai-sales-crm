"""CRM reporting: stats computed from the persisted conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from .messaging.handling import HANDLER_HUMAN
from .models import ROLE_INBOUND, ROLE_OUTBOUND, Conversation, Customer, Message

NEW_CUSTOMER_DAYS = 7


@dataclass(frozen=True)
class ReportSummary:
    total_customers: int
    new_customers: int
    high_intent: int
    quotes_sent: int
    handoffs: int
    reply_rate: float
    ai_reply_success_rate: float
    countries: dict[str, int]


class ReportService:
    """Computes the CRM dashboard summary from current data."""

    def __init__(self, session: Session, *, fallback_reply: str) -> None:
        self._session = session
        self._fallback_reply = fallback_reply

    def summary(self, now: datetime | None = None) -> ReportSummary:
        now = _aware(now or datetime.now(UTC))
        customers = list(self._session.exec(select(Customer)).all())
        conversations = list(self._session.exec(select(Conversation)).all())
        messages = list(self._session.exec(select(Message)).all())

        inbound_counts: dict[int, int] = {}
        outbound_counts: dict[int, int] = {}
        fallback_outbound = 0
        for message in messages:
            if message.role == ROLE_INBOUND:
                inbound_counts[message.conversation_id] = (
                    inbound_counts.get(message.conversation_id, 0) + 1
                )
            elif message.role == ROLE_OUTBOUND:
                outbound_counts[message.conversation_id] = (
                    outbound_counts.get(message.conversation_id, 0) + 1
                )
                if message.content == self._fallback_reply:
                    fallback_outbound += 1

        total = len(conversations)
        engaged = sum(1 for c in conversations if inbound_counts.get(c.id, 0) >= 2)
        total_outbound = sum(outbound_counts.values())

        countries: dict[str, int] = {}
        for customer in customers:
            if customer.country_code:
                countries[customer.country_code] = countries.get(customer.country_code, 0) + 1

        return ReportSummary(
            total_customers=len(customers),
            new_customers=sum(
                1
                for c in customers
                if _aware(c.created_at) >= now - timedelta(days=NEW_CUSTOMER_DAYS)
            ),
            high_intent=sum(1 for c in customers if c.lead_level == "high"),
            quotes_sent=sum(1 for c in conversations if c.quote_sent),
            handoffs=sum(1 for c in conversations if c.handler == HANDLER_HUMAN),
            reply_rate=round(engaged / total, 4) if total else 0.0,
            ai_reply_success_rate=(
                round((total_outbound - fallback_outbound) / total_outbound, 4)
                if total_outbound
                else 0.0
            ),
            countries=countries,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
