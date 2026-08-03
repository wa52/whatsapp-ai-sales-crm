from datetime import timedelta

from fakes import FakeLLM
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from whatsapp_ai_sales.api.followup import start_followup_scheduler
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.models import Message
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider


def _app() -> tuple[TestClient, MockWhatsAppProvider, object]:
    llm = FakeLLM(content="ok")
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=llm, provider=provider)
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "LED Strip", "sections": {"intro": "A light strip, 5m reel."}},
    )
    product_id = client.get("/api/kb/products").json()[0]["id"]
    client.post(
        f"/api/pricing/products/{product_id}/rule",
        json={
            "standard_price": 10.0,
            "min_price": 6.0,
            "auto_deal_price": 6.5,
            "tiers": [{"min_quantity": 100, "unit_price": 8.0}],
        },
    )
    return client, provider, app


def _send(client: TestClient, text: str = "what is the price of LED strip?") -> None:
    client.post(
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
                                        "id": "wamid.followup",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            }
                        }
                    ],
                }
            ],
        },
    )


def _conversation_id(client: TestClient) -> int:
    return client.get("/api/crm/conversations").json()[0]["id"]


def _backdate_messages(app: object, hours: int = 25) -> None:
    with Session(app.state.engine) as session:
        for message in session.exec(select(Message)).all():
            message.created_at = message.created_at - timedelta(hours=hours)
        session.commit()


def test_run_endpoint_sends_due_followup() -> None:
    client, provider, app = _app()
    _send(client)
    _backdate_messages(app)

    response = client.post("/api/followups/run")

    assert response.json() == {"sent": 1}
    assert provider.sent[-1].text == (
        "Hello! Just following up on your inquiry. Would you like more information or a quote?"
    )


def test_run_skips_dnd_conversation() -> None:
    client, provider, app = _app()
    _send(client)
    conversation_id = _conversation_id(client)
    client.post(f"/api/crm/conversations/{conversation_id}/dnd", json={"enabled": True})
    _backdate_messages(app)
    sent_before = len(provider.sent)

    assert client.post("/api/followups/run").json() == {"sent": 0}
    assert len(provider.sent) == sent_before


def test_dnd_endpoint_roundtrip() -> None:
    client, _, _ = _app()
    _send(client)
    conversation_id = _conversation_id(client)

    response = client.post(
        f"/api/crm/conversations/{conversation_id}/dnd", json={"enabled": True}
    )

    assert response.json()["dnd"] is True
    assert client.post(
        f"/api/crm/conversations/{conversation_id}/dnd", json={"enabled": False}
    ).json()["dnd"] is False


def test_quote_followup_after_quote_sent() -> None:
    client, provider, app = _app()
    _send(client, "I need 200 pcs of LED strip, what is the price?")
    _backdate_messages(app, hours=50)

    client.post("/api/followups/run")

    assert provider.sent[-1].text == (
        "Hi! We sent you a quote earlier. Would you like to proceed or need any adjustments?"
    )


def test_scheduler_registers_followup_job() -> None:
    client, _, app = _app()

    start_followup_scheduler(app)
    try:
        jobs = app.state.scheduler.get_jobs()
        assert [job.id for job in jobs] == ["followup_job"]
    finally:
        app.state.scheduler.shutdown(wait=False)
