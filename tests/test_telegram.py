import json

import httpx

from whatsapp_ai_sales.telegram.bot import TelegramBot
from whatsapp_ai_sales.telegram.poller import TelegramPoller, update_to_inbound


def _text_update(update_id: int = 5, chat_id: int = 123, text: str = "Hello") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "date": 1700000000,
            "text": text,
            "chat": {"id": chat_id},
            "from": {"first_name": "Anna"},
        },
    }


def test_update_to_inbound_text() -> None:
    inbound = update_to_inbound(_text_update())

    assert inbound is not None
    assert inbound.wa_id == "123"
    assert inbound.message_id == "tg-5"
    assert inbound.text == "Hello"
    assert inbound.profile_name == "Anna"
    assert inbound.timestamp == 1700000000


def test_update_to_inbound_ignores_photo_and_edited() -> None:
    photo = {
        "update_id": 6,
        "message": {"message_id": 11, "date": 1, "chat": {"id": 1}, "photo": []},
    }
    edited = {"update_id": 7, "edited_message": {"text": "hi"}}
    assert update_to_inbound(photo) is None
    assert update_to_inbound(edited) is None


def test_send_message_posts_to_bot_api() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    bot = TelegramBot("token123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    message_id = bot.send_message("123", "hi")

    assert message_id == "42"
    assert "token123" in captured["url"]
    assert "/sendMessage" in captured["url"]
    assert captured["body"] == {"chat_id": "123", "text": "hi"}


def test_get_updates_passes_offset() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"ok": True, "result": [{"update_id": 3}, {"update_id": 4}]},
        )

    bot = TelegramBot("token123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    updates = bot.get_updates(offset=3)

    assert len(updates) == 2
    assert captured["params"]["offset"] == "3"


def test_poller_dispatches_and_advances_offset() -> None:
    class FakeBot:
        def get_updates(self, offset, timeout=0):
            return [_text_update(update_id=5)]

    handled = []
    poller = TelegramPoller(FakeBot(), handled.append)

    count = poller.poll_once()

    assert count == 1
    assert handled[0].wa_id == "123"
    assert poller._offset == 6
