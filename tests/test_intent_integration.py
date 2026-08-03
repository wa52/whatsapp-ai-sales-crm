from fakes import ConditionalLLM, FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.config import Settings
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider


def _client() -> tuple[TestClient, MockWhatsAppProvider]:
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=FakeLLM(content="ok"), provider=provider)
    return TestClient(app), provider


def _meta(text: str, wa_id: str = "4912345678", message_id: str = "wamid.1") -> dict:
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
                            "contacts": [{"profile": {"name": "John"}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
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


def test_price_and_quantity_message_scores_low() -> None:
    client, _ = _client()

    client.post(
        "/webhooks/whatsapp",
        json=_meta("I need 500 pieces shipped to Germany. What is the price?"),
    )

    rows = client.get("/api/crm/conversations").json()
    assert rows[0]["lead_score"] == 35
    assert rows[0]["lead_level"] == "low"


def test_rich_message_scores_high() -> None:
    client, _ = _client()

    client.post(
        "/webhooks/whatsapp",
        json=_meta(
            "We need 500 pieces this month, budget around 5000 usd. "
            "What is the price? Please send a sample. How about shipping and payment?"
        ),
    )

    rows = client.get("/api/crm/conversations").json()
    assert rows[0]["lead_score"] == 75
    assert rows[0]["lead_level"] == "high"


def test_profile_accumulates_across_messages() -> None:
    client, _ = _client()

    client.post("/webhooks/whatsapp", json=_meta("What is the price?", message_id="wamid.1"))
    client.post(
        "/webhooks/whatsapp",
        json=_meta("I need 500 pieces", message_id="wamid.2"),
    )

    rows = client.get("/api/crm/conversations").json()
    # second message adds quantity: 20(quote) + 15(quantity) - 0 = 35; message_count=2
    assert rows[0]["lead_score"] == 35


def test_reply_frequency_raises_score() -> None:
    client, _ = _client()

    for i, text in enumerate(["hi", "do you have stock?", "what is the price?"], start=1):
        client.post("/webhooks/whatsapp", json=_meta(text, message_id=f"wamid.{i}"))

    rows = client.get("/api/crm/conversations").json()
    assert rows[0]["lead_score"] == 25  # 20 quote + 10 (3 replies) - 5 (no qty/time)
    assert rows[0]["lead_level"] == "low"


def test_kb_product_name_populates_interested_product() -> None:
    client, _ = _client()
    client.post(
        "/api/kb/products", json={"name": "LED Strip", "sections": {"intro": "A light strip."}}
    )

    client.post("/webhooks/whatsapp", json=_meta("How much for LED strip?"))

    rows = client.get("/api/crm/conversations").json()
    assert rows[0]["interested_product"] == "LED Strip"


def test_llm_intent_extraction_used_when_enabled() -> None:
    llm = ConditionalLLM(reply="ok", json_payload={"need_quote": True, "quantity": 42})
    settings = Settings(intent_llm_extract=True, fallback_reply="FALLBACK")
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=llm, provider=provider, settings=settings)
    client = TestClient(app)

    client.post("/webhooks/whatsapp", json=_meta("hello"))

    rows = client.get("/api/crm/conversations").json()
    # reply path had no knowledge so it fell back; the extractor used the LLM JSON
    assert provider.sent[0].text == "FALLBACK"
    assert rows[0]["lead_score"] == 35  # quote 20 + quantity 15
    assert len(llm.calls) == 1
