"""Telegram Bot API client. `send_message` satisfies the WhatsAppProvider seam,
so Telegram chat ids are treated as the customer's `wa_id`."""

from __future__ import annotations

import httpx

API_BASE = "https://api.telegram.org/bot{token}"


class TelegramBot:
    """Thin httpx client for the Telegram Bot API."""

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        proxy: str | None = None,
    ) -> None:
        self._token = token
        self._client = client or httpx.Client(proxy=proxy, timeout=30)

    def _url(self, method: str) -> str:
        return f"{API_BASE.format(token=self._token)}/{method}"

    def send_message(self, to: str, text: str) -> str:
        """Send a text message to a chat; returns the Telegram message id."""
        response = self._client.post(
            self._url("sendMessage"), json={"chat_id": to, "text": text}
        )
        response.raise_for_status()
        return str(response.json()["result"]["message_id"])

    def get_updates(self, offset: int = 0, timeout: int = 10) -> list[dict]:
        """Long-poll for new updates, advancing the caller's offset."""
        response = self._client.get(
            self._url("getUpdates"), params={"offset": offset, "timeout": timeout}
        )
        response.raise_for_status()
        return response.json().get("result", [])

    def get_me(self) -> dict:
        """Verify the token and return the bot's identity."""
        response = self._client.get(self._url("getMe"))
        response.raise_for_status()
        return response.json()["result"]


__all__ = ["TelegramBot"]
