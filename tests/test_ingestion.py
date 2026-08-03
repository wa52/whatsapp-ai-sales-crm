from sqlmodel import Session, SQLModel, select

from whatsapp_ai_sales.db import create_engine_for
from whatsapp_ai_sales.messaging.agent import AutoReplyAgent
from whatsapp_ai_sales.messaging.ingestion import MessageIngestion
from whatsapp_ai_sales.models import Conversation, Customer, Message
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider
from whatsapp_ai_sales.whatsapp.webhook import InboundMessage

SYSTEM_PROMPT = "You are a sales assistant."
FALLBACK = "I will confirm with sales and reply shortly."


class FakeLLM:
    def __init__(self, *, content: str = "ok", error: Exception | None = None) -> None:
        self._content = content
        self._error = error

    def chat(self, messages: list[dict]) -> str:
        if self._error is not None:
            raise self._error
        return self._content


def _setup(llm: FakeLLM | None = None) -> tuple[MessageIngestion, MockWhatsAppProvider]:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    llm = llm or FakeLLM(content="The price is $8 each.")
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)
    provider = MockWhatsAppProvider()
    session = Session(engine)
    ingestion = MessageIngestion(session=session, agent=agent, provider=provider)
    return ingestion, provider


def _inbound(message_id: str = "wamid.1", wa_id: str = "4912345678") -> InboundMessage:
    return InboundMessage(
        wa_id=wa_id, message_id=message_id, timestamp=1700000000, text="Price?"
    )


def test_processes_first_message_end_to_end() -> None:
    ingestion, provider = _setup()

    result = ingestion.handle_inbound(_inbound())

    assert result.handled is True
    assert result.reply_text == "The price is $8 each."
    assert len(provider.sent) == 1
    _, to, text = provider.sent[0]
    assert to == "4912345678"
    assert text == "The price is $8 each."

    customers = ingestion.session.exec(select(Customer)).all()
    conversations = ingestion.session.exec(select(Conversation)).all()
    messages = ingestion.session.exec(select(Message)).all()
    assert len(customers) == 1
    assert len(conversations) == 1
    assert {m.role for m in messages} == {"inbound", "outbound"}


def test_duplicate_message_id_is_skipped() -> None:
    ingestion, provider = _setup()

    first = ingestion.handle_inbound(_inbound(message_id="wamid.dup"))
    second = ingestion.handle_inbound(_inbound(message_id="wamid.dup"))

    assert first.handled is True
    assert second.handled is False
    assert len(provider.sent) == 1
    assert len(ingestion.session.exec(select(Message)).all()) == 2


def test_reuses_customer_and_conversation_for_same_wa_id() -> None:
    ingestion, _ = _setup()

    ingestion.handle_inbound(_inbound(message_id="wamid.1"))
    ingestion.handle_inbound(_inbound(message_id="wamid.2"))

    customers = ingestion.session.exec(select(Customer)).all()
    conversations = ingestion.session.exec(select(Conversation)).all()
    assert len(customers) == 1
    assert len(conversations) == 1


def test_llm_failure_still_persists_with_fallback_reply() -> None:
    llm = FakeLLM(error=RuntimeError("upstream down"))
    ingestion, provider = _setup(llm)

    result = ingestion.handle_inbound(_inbound())

    assert result.handled is True
    assert result.reply_text == FALLBACK
    assert provider.sent[-1][2] == FALLBACK
