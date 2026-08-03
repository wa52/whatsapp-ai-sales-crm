"""Scheduled customer follow-ups: when to chase a silent customer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from ..models import ROLE_OUTBOUND, Conversation, Customer, Message
from ..repos import send_outbound_message, touch
from ..whatsapp.base import WhatsAppProvider
from .handling import HANDLER_AI

KIND_NO_REPLY = "no_reply"
KIND_QUOTE_FOLLOWUP = "quote_followup"


@dataclass(frozen=True)
class FollowUpDraft:
    kind: str
    message: str


def due_followup(
    *,
    handler: str,
    dnd: bool,
    followups_sent: int,
    last_message_role: str,
    last_message_at: datetime,
    now: datetime,
    quote_sent: bool = False,
    no_reply_hours: int = 24,
    quote_followup_hours: int = 48,
    max_followups: int = 2,
    no_reply_message: str,
    quote_followup_message: str,
) -> FollowUpDraft | None:
    """Decide whether a follow-up is due for a conversation waiting on the customer.

    Never follows up when a human owns the conversation, the customer muted it,
    the follow-up budget is exhausted, or the last word came from the customer.
    """
    if handler != HANDLER_AI or dnd:
        return None
    if followups_sent >= max_followups:
        return None
    if last_message_role != ROLE_OUTBOUND:
        return None

    elapsed = _aware(now) - _aware(last_message_at)
    if quote_sent and elapsed >= timedelta(hours=quote_followup_hours):
        return FollowUpDraft(kind=KIND_QUOTE_FOLLOWUP, message=quote_followup_message)
    if elapsed >= timedelta(hours=no_reply_hours):
        return FollowUpDraft(kind=KIND_NO_REPLY, message=no_reply_message)
    return None


def _aware(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. read back from SQLite) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class FollowUpRunner:
    """Scans active conversations and sends one due follow-up per conversation."""

    def __init__(
        self,
        session: Session,
        provider: WhatsAppProvider,
        *,
        no_reply_hours: int,
        quote_hours: int,
        max_followups: int,
        no_reply_message: str,
        quote_followup_message: str,
    ) -> None:
        self._session = session
        self._provider = provider
        self._no_reply_hours = no_reply_hours
        self._quote_hours = quote_hours
        self._max_followups = max_followups
        self._no_reply_message = no_reply_message
        self._quote_followup_message = quote_followup_message

    def run_due(self, now: datetime | None = None) -> int:
        """Send every currently due follow-up; returns how many were sent.

        Commits per conversation so a provider failure mid-scan never loses the
        record of follow-ups already delivered (and thus never re-sends them).
        """
        now = now or datetime.now(UTC)
        sent = 0
        conversations = self._session.exec(
            select(Conversation).where(Conversation.status == "active")
        ).all()
        for conversation in conversations:
            last = self._session.exec(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            ).first()
            if last is None:
                continue

            draft = due_followup(
                handler=conversation.handler,
                dnd=conversation.dnd,
                followups_sent=conversation.followups_sent,
                last_message_role=last.role,
                last_message_at=last.created_at,
                now=now,
                quote_sent=conversation.quote_sent,
                no_reply_hours=self._no_reply_hours,
                quote_followup_hours=self._quote_hours,
                max_followups=self._max_followups,
                no_reply_message=self._no_reply_message,
                quote_followup_message=self._quote_followup_message,
            )
            if draft is None:
                continue
            customer = self._session.get(Customer, conversation.customer_id)
            if customer is None:
                continue
            send_outbound_message(
                self._session, self._provider, conversation, customer, draft.message
            )
            conversation.followups_sent += 1
            touch(conversation)
            self._session.commit()
            sent += 1

        return sent
