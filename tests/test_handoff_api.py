from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.messaging.notification import RecordingNotifier
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

RULE = {
    "currency": "USD",
    "standard_price": 10.0,
    "min_price": 6.0,
    "auto_deal_price": 6.5,
    "sample_price": 15.0,
    "discount_allowed": True,
    "tiers": [{"min_quantity": 100, "unit_price": 8.0}],
}


def _app() -> tuple[TestClient, FakeLLM, MockWhatsAppProvider, RecordingNotifier]:
    llm = FakeLLM(content="ok")
    provider = MockWhatsAppProvider()
    notifier = RecordingNotifier()
    app = create_app(
        db_url="sqlite://",
        llm=llm,
        provider=provider,
        notifier=notifier,
        settings=__import__("whatsapp_ai_sales.config", fromlist=["Settings"]).Settings(
            fallback_reply="SALES_FALLBACK"
        ),
    )
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "LED Strip", "sections": {"intro": "A light strip, 5m reel."}},
    )
    product_id = client.get("/api/kb/products").json()[0]["id"]
    client.post(f"/api/pricing/products/{product_id}/rule", json=RULE)
    return client, llm, provider, notifier


def _meta(text: str, message_id: str = "wamid.1") -> dict:
    return {
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
                                    "id": message_id,
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
    }


def _conversation_id(client: TestClient) -> int:
    return client.get("/api/crm/conversations").json()[0]["id"]


def test_takeover_stops_ai_auto_reply() -> None:
    client, llm, provider, _ = _app()
    client.post("/webhooks/whatsapp", json=_meta("what is the price of LED strip?"))
    conversation_id = _conversation_id(client)
    llm.calls.clear()

    client.post(f"/api/crm/conversations/{conversation_id}/takeover")
    sent_before = len(provider.sent)
    client.post("/webhooks/whatsapp", json=_meta("still there?", message_id="wamid.2"))

    assert len(llm.calls) == 0
    assert len(provider.sent) == sent_before  # no new outbound from the AI
    assert client.get("/api/crm/conversations").json()[0]["handler"] == "human"


def test_release_restores_ai_reply() -> None:
    client, llm, provider, _ = _app()
    client.post("/webhooks/whatsapp", json=_meta("what is the price of LED strip?"))
    conversation_id = _conversation_id(client)
    client.post(f"/api/crm/conversations/{conversation_id}/takeover")
    client.post(f"/api/crm/conversations/{conversation_id}/release")
    llm.calls.clear()

    client.post("/webhooks/whatsapp", json=_meta("LED strip price?", message_id="wamid.2"))

    assert len(llm.calls) == 1
    assert len(provider.sent) >= 1


def test_manual_message_sends_via_provider() -> None:
    client, _, provider, _ = _app()
    client.post("/webhooks/whatsapp", json=_meta("hello"))
    conversation_id = _conversation_id(client)

    response = client.post(
        f"/api/crm/conversations/{conversation_id}/messages",
        json={"content": "Hello! This is our sales rep."},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "outbound"
    assert provider.sent[-1].to == "4912345678"
    assert provider.sent[-1].text == "Hello! This is our sales rep."


def test_low_offer_auto_hands_off_to_human() -> None:
    client, _, _, notifier = _app()

    client.post(
        "/webhooks/whatsapp",
        json=_meta("I need 200 pcs of LED strip, can you do 3 USD?"),
    )

    rows = client.get("/api/crm/conversations").json()
    assert rows[0]["handler"] == "human"
    kinds = [e.kind for e in notifier.events]
    assert "handoff" in kinds


def test_negative_customer_auto_hands_off() -> None:
    client, _, _, notifier = _app()

    client.post(
        "/webhooks/whatsapp",
        json=_meta("The LED strip is too expensive!"),
    )

    assert client.get("/api/crm/conversations").json()[0]["handler"] == "human"
    assert "handoff" in [e.kind for e in notifier.events]


def test_high_lead_emits_notification() -> None:
    client, _, _, notifier = _app()

    client.post(
        "/webhooks/whatsapp",
        json=_meta(
            "We need 500 pcs of LED strip this month, budget 5000 usd, "
            "what is the price? send a sample, how about shipping and payment?"
        ),
    )

    kinds = [e.kind for e in notifier.events]
    assert "lead_high" in kinds
