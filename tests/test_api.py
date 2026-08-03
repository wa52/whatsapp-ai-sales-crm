from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

META_PAYLOAD = {
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
                        "contacts": [{"profile": {"name": "John Doe"}, "wa_id": "4912345678"}],
                        "messages": [
                            {
                                "from": "4912345678",
                                "id": "wamid.ABC",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "What is the price?"},
                            }
                        ],
                    }
                }
            ],
        }
    ],
}


def _app() -> tuple[TestClient, MockWhatsAppProvider]:
    provider = MockWhatsAppProvider()
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="The price is $8 each."),
        provider=provider,
    )
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "Widget", "sections": {"price": "The price is $8 each."}},
    )
    return client, provider


def test_webhook_processes_message_and_sends_reply() -> None:
    client, provider = _app()

    response = client.post("/webhooks/whatsapp", json=META_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(provider.sent) == 1
    assert provider.sent[0].to == "4912345678"
    assert provider.sent[0].text == "The price is $8 each."


def test_duplicate_webhook_does_not_send_twice() -> None:
    client, provider = _app()

    client.post("/webhooks/whatsapp", json=META_PAYLOAD)
    client.post("/webhooks/whatsapp", json=META_PAYLOAD)

    assert len(provider.sent) == 1


def test_crm_lists_conversations_with_customer() -> None:
    client, _ = _app()
    client.post("/webhooks/whatsapp", json=META_PAYLOAD)

    response = client.get("/api/crm/conversations")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["wa_id"] == "4912345678"
    assert rows[0]["customer_name"] == "John Doe"
    assert rows[0]["country_code"] == "DE"
    assert rows[0]["handler"] == "ai"


def test_crm_lists_most_recent_conversation_first() -> None:
    client, _ = _app()
    client.post("/webhooks/whatsapp", json=META_PAYLOAD)
    recent = dict(META_PAYLOAD)
    recent["entry"] = [
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
                        "contacts": [{"profile": {"name": "Li Wei"}, "wa_id": "8613800000000"}],
                        "messages": [
                            {
                                "from": "8613800000000",
                                "id": "wamid.XYZ",
                                "timestamp": "1700000100",
                                "type": "text",
                                "text": {"body": "Hello"},
                            }
                        ],
                    }
                }
            ],
        }
    ]
    client.post("/webhooks/whatsapp", json=recent)

    rows = client.get("/api/crm/conversations").json()

    assert [r["wa_id"] for r in rows] == ["8613800000000", "4912345678"]


def test_crm_lists_conversation_messages() -> None:
    client, _ = _app()
    client.post("/webhooks/whatsapp", json=META_PAYLOAD)

    conversations = client.get("/api/crm/conversations").json()
    conversation_id = conversations[0]["id"]
    response = client.get(f"/api/crm/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    messages = response.json()
    assert [m["role"] for m in messages] == ["inbound", "outbound"]
    assert messages[0]["content"] == "What is the price?"
    assert messages[1]["content"] == "The price is $8 each."
    assert messages[0]["status"] == "received"
    assert messages[1]["status"] == "sent"


def test_crm_messages_404_for_missing_conversation() -> None:
    client, _ = _app()

    response = client.get("/api/crm/conversations/999/messages")

    assert response.status_code == 404


def test_webhook_verification_get_handshake() -> None:
    client, _ = _app()

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "123456789",
        },
    )

    assert response.status_code == 200
    assert response.text == "123456789"


def test_webhook_verification_rejects_bad_token() -> None:
    client, _ = _app()

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "123456789",
        },
    )

    assert response.status_code == 403
