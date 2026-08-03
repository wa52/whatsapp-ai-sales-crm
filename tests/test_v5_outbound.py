from fakes import FakeLLM
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from whatsapp_ai_sales.config import Settings
from whatsapp_ai_sales.db import create_engine_for
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.messaging.outbound import retry_failed_outbound, send_with_retry
from whatsapp_ai_sales.models import (
    ROLE_OUTBOUND,
    STATUS_FAILED,
    STATUS_SENT,
    Conversation,
    Customer,
    Message,
)
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider


class FailingThenWorking:
    def __init__(self, failures: int = 2) -> None:
        self.failures = failures
        self.calls = 0
        self.sent: list[tuple[str, str]] = []

    def send_message(self, to: str, text: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("provider down")
        self.sent.append((to, text))
        return f"mid-{self.calls}"


class AlwaysFailing:
    def send_message(self, to: str, text: str) -> str:
        raise RuntimeError("provider down")


def _conv(session: Session) -> tuple[Conversation, Customer]:
    customer = Customer(wa_id="4912345678", country_code="DE")
    session.add(customer)
    session.flush()
    conversation = Conversation(customer_id=customer.id, status="active", handler="ai")
    session.add(conversation)
    session.flush()
    return conversation, customer


def test_send_with_retry_recovers_from_transient_errors() -> None:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    conversation, customer = _conv(session)
    provider = FailingThenWorking(failures=2)

    message = send_with_retry(
        session, provider, conversation, customer, "hi", max_attempts=3
    )

    assert provider.calls == 3
    assert message.status == STATUS_SENT
    assert provider.sent == [("4912345678", "hi")]


def test_ingestion_survives_provider_failure_and_records_failed() -> None:
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="ok"),
        provider=AlwaysFailing(),
        settings=Settings(fallback_reply="FALLBACK"),
    )
    client = TestClient(app)
    response = client.post(
        "/webhooks/whatsapp",
        json={
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "PHONE_NUMBER_ID",
                                },
                                "contacts": [{"profile": {"name": "John"}, "wa_id": "4912345678"}],
                                "messages": [
                                    {
                                        "from": "4912345678",
                                        "id": "wamid.v5",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": "hello"},
                                    }
                                ],
                            }
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    conversation_id = client.get("/api/crm/conversations").json()[0]["id"]
    messages = client.get(f"/api/crm/conversations/{conversation_id}/messages").json()
    statuses = {m["status"] for m in messages}
    assert "failed" in statuses  # inbound persisted, outbound marked failed


def test_retry_failed_outbound_resends() -> None:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    conversation, customer = _conv(session)
    session.add(
        Message(
            conversation_id=conversation.id,
            role=ROLE_OUTBOUND,
            content="please confirm",
            status=STATUS_FAILED,
            attempts=1,
        )
    )
    session.commit()
    provider = MockWhatsAppProvider()

    count = retry_failed_outbound(session, provider, max_attempts=2)

    assert count == 1
    message = session.exec(select(Message).where(Message.role == ROLE_OUTBOUND)).first()
    assert message.status == STATUS_SENT
    assert provider.sent[-1].text == "please confirm"


def test_retry_stops_at_max_attempts() -> None:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    conversation, customer = _conv(session)
    session.add(
        Message(
            conversation_id=conversation.id,
            role=ROLE_OUTBOUND,
            content="nope",
            status=STATUS_FAILED,
            attempts=2,
        )
    )
    session.commit()

    count = retry_failed_outbound(session, MockWhatsAppProvider(), max_attempts=2)

    assert count == 0
