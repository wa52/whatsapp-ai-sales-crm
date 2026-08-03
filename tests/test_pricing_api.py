from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

RULE = {
    "currency": "USD",
    "standard_price": 10.0,
    "min_price": 6.0,
    "auto_deal_price": 6.5,
    "sample_price": 15.0,
    "discount_allowed": True,
    "tiers": [
        {"min_quantity": 100, "unit_price": 8.0},
        {"min_quantity": 500, "unit_price": 6.5},
    ],
}


def _app() -> tuple[TestClient, FakeLLM, MockWhatsAppProvider]:
    llm = FakeLLM(content="ok")
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=llm, provider=provider)
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "LED Strip", "sections": {"intro": "A light strip, 5m reel."}},
    )
    product_id = client.get("/api/kb/products").json()[0]["id"]
    client.post(f"/api/pricing/products/{product_id}/rule", json=RULE)
    return client, llm, provider


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


def test_pricing_api_roundtrip() -> None:
    client, _, _ = _app()
    product_id = client.get("/api/kb/products").json()[0]["id"]

    rule = client.get(f"/api/pricing/products/{product_id}/rule").json()

    assert rule["standard_price"] == 10.0
    assert rule["min_price"] == 6.0
    assert [t["min_quantity"] for t in rule["tiers"]] == [100, 500]


def test_pricing_api_404_without_rule() -> None:
    client, _, _ = _app()
    client.post(
        "/api/kb/products", json={"name": "Other", "sections": {"intro": "x"}}
    )
    other_id = client.get("/api/kb/products").json()[1]["id"]

    response = client.get(f"/api/pricing/products/{other_id}/rule")

    assert response.status_code == 404


def test_quote_message_grounded_in_computed_price() -> None:
    client, llm, provider = _app()

    client.post("/webhooks/whatsapp", json=_meta("I need 500 pcs of LED strip, what is the price?"))

    assert len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "6.50 USD/unit" in system
    assert "3250.00 USD" in system
    assert provider.sent[0].text == "ok"


def test_low_offer_routes_to_human_verdict() -> None:
    client, llm, provider = _app()

    client.post(
        "/webhooks/whatsapp",
        json=_meta("I need 500 pcs of LED strip, can you do 5 USD?"),
    )

    assert len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "Verdict: human" in system
    assert "below the minimum" in system


def test_acceptable_offer_verdict() -> None:
    client, llm, _ = _app()

    client.post(
        "/webhooks/whatsapp",
        json=_meta("I need 500 pcs of LED strip, can you do 6.8 USD?"),
    )

    system = llm.calls[0][0]["content"]
    assert "Verdict: accept" in system
