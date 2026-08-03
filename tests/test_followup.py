from datetime import UTC, datetime, timedelta

from sqlmodel import Session, SQLModel, select

from whatsapp_ai_sales.db import create_engine_for
from whatsapp_ai_sales.messaging.followup import (
    KIND_NO_REPLY,
    KIND_QUOTE_FOLLOWUP,
    FollowUpRunner,
    due_followup,
)
from whatsapp_ai_sales.messaging.handling import HANDLER_AI, HANDLER_HUMAN
from whatsapp_ai_sales.models import ROLE_OUTBOUND, Conversation, Customer, Message
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
NO_REPLY = "following up on your inquiry"
QUOTE = "following up on your quote"


def _hours_ago(hours: int) -> datetime:
    return NOW - timedelta(hours=hours)


def _draft(handler: str = HANDLER_AI, **overrides):
    params = dict(
        handler=handler,
        dnd=False,
        followups_sent=0,
        last_message_role=ROLE_OUTBOUND,
        last_message_at=_hours_ago(25),
        now=NOW,
        quote_sent=False,
        no_reply_hours=24,
        quote_followup_hours=48,
        max_followups=2,
        no_reply_message=NO_REPLY,
        quote_followup_message=QUOTE,
    )
    params.update(overrides)
    return due_followup(**params)
class TestDueFollowup:
    def test_not_due_when_last_message_is_inbound(self) -> None:
        assert _draft(last_message_role="inbound") is None

    def test_not_due_before_threshold(self) -> None:
        assert _draft(last_message_at=_hours_ago(1)) is None

    def test_no_reply_due_after_threshold(self) -> None:
        draft = _draft()
        assert draft is not None
        assert draft.kind == KIND_NO_REPLY
        assert draft.message == NO_REPLY

    def test_quote_followup_preferred_when_pending(self) -> None:
        draft = _draft(quote_sent=True, last_message_at=_hours_ago(50))
        assert draft is not None
        assert draft.kind == KIND_QUOTE_FOLLOWUP
        assert draft.message == QUOTE

    def test_skips_human_handler(self) -> None:
        assert _draft(handler=HANDLER_HUMAN) is None

    def test_skips_dnd(self) -> None:
        assert _draft(dnd=True) is None

    def test_skips_when_over_max_followups(self) -> None:
        assert _draft(followups_sent=2) is None


def _setup() -> tuple[Session, Conversation, MockWhatsAppProvider]:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    customer = Customer(wa_id="4912345678", country_code="DE")
    session.add(customer)
    session.flush()
    conversation = Conversation(customer_id=customer.id, status="active", handler="ai")
    session.add(conversation)
    session.flush()
    session.add(
        Message(
            conversation_id=conversation.id,
            role=ROLE_OUTBOUND,
            content="Here is the price.",
            status="sent",
            created_at=_hours_ago(25),
        )
    )
    session.commit()
    return session, conversation, MockWhatsAppProvider()


def _runner(session: Session, provider: MockWhatsAppProvider) -> FollowUpRunner:
    return FollowUpRunner(
        session,
        provider,
        no_reply_hours=24,
        quote_hours=48,
        max_followups=2,
        no_reply_message=NO_REPLY,
        quote_followup_message=QUOTE,
    )


class TestRunner:
    def test_sends_due_followup_once(self) -> None:
        session, conversation, provider = _setup()
        runner = _runner(session, provider)

        count = runner.run_due(NOW)

        assert count == 1
        assert provider.sent[-1].to == "4912345678"
        assert provider.sent[-1].text == NO_REPLY
        assert conversation.followups_sent == 1
        outbound = session.exec(
            select(Message).where(Message.conversation_id == conversation.id)
        ).all()
        assert outbound[-1].content == NO_REPLY

    def test_does_not_resend_within_cooldown(self) -> None:
        session, _, provider = _setup()
        runner = _runner(session, provider)

        assert runner.run_due(NOW) == 1
        assert runner.run_due(NOW) == 0  # last message just moved to now

    def test_skips_human_and_dnd_conversations(self) -> None:
        session, conversation, provider = _setup()
        human = Conversation(customer_id=conversation.customer_id, status="active",
                             handler=HANDLER_HUMAN)
        dnd = Conversation(customer_id=conversation.customer_id, status="active",
                           handler="ai", dnd=True)
        session.add_all([human, dnd])
        session.commit()
        runner = _runner(session, provider)

        assert runner.run_due(NOW) == 1
        assert human.followups_sent == 0
        assert dnd.followups_sent == 0

    def test_stops_at_max_followups(self) -> None:
        session, conversation, provider = _setup()
        conversation.followups_sent = 2
        session.commit()
        runner = _runner(session, provider)

        assert runner.run_due(NOW) == 0
