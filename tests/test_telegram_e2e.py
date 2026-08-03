import json

import httpx
from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.config import Settings
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.telegram.bot import TelegramBot
from whatsapp_ai_sales.telegram.runtime import build_poller
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider


def _bot_with_api(inbound_text: str) -> tuple[TelegramBot, list[dict]]:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sendMessage"):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 1,
                            "message": {
                                "message_id": 10,
                                "date": 1700000000,
                                "text": inbound_text,
                                "chat": {"id": "tguser1"},
                                "from": {"first_name": "John"},
                            },
                        }
                    ],
                },
            )
        return httpx.Response(404)

    bot = TelegramBot("token123", client=httpx.Client(transport=httpx.MockTransport(handler)))
    return bot, sent


def test_telegram_message_is_answered_end_to_end() -> None:
    bot, sent = _bot_with_api("what is the price of LED strip?")
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="The price is 8 USD."),
        provider=bot,
        settings=Settings(fallback_reply="FALLBACK"),
    )
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "LED Strip", "sections": {"intro": "LED strip 5m reel."}},
    )
    product_id = client.get("/api/kb/products").json()[0]["id"]
    client.post(
        f"/api/pricing/products/{product_id}/rule",
        json={"standard_price": 10.0, "min_price": 6.0, "auto_deal_price": 6.5,
              "tiers": [{"min_quantity": 100, "unit_price": 8.0}]},
    )

    build_poller(app).poll_once()

    assert sent, "no outbound was sent"
    assert sent[-1]["chat_id"] == "tguser1"
    assert sent[-1]["text"] == "The price is 8 USD."

    conversations = client.get("/api/crm/conversations").json()
    assert conversations[0]["wa_id"] == "tguser1"
    assert conversations[0]["interested_product"] == "LED Strip"


def test_telegram_bot_as_default_provider_when_token_set() -> None:
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="ok"),
        settings=Settings(telegram_token="tok"),
    )
    from whatsapp_ai_sales.telegram.bot import TelegramBot

    assert isinstance(app.state.provider, TelegramBot)


def test_telegram_disabled_without_token_uses_mock() -> None:
    app = create_app(db_url="sqlite://", llm=FakeLLM(content="ok"), provider=MockWhatsAppProvider())
    assert isinstance(app.state.provider, MockWhatsAppProvider)


def test_manual_poll_endpoint() -> None:
    bot, sent = _bot_with_api("hello")
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="ok"),
        provider=bot,
        settings=Settings(fallback_reply="FALLBACK"),
    )
    client = TestClient(app)

    response = client.post("/api/telegram/poll")

    assert response.status_code == 200
    assert response.json() == {"handled": 1}
    assert sent and sent[-1]["chat_id"] == "tguser1"
