"""Telegram long-polling: turn bot updates into inbound messages and dispatch them."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..whatsapp.webhook import InboundMessage

logger = logging.getLogger(__name__)


def update_to_inbound(update: dict) -> InboundMessage | None:
    """Convert a Telegram update to an InboundMessage, or None if not a text message."""
    message = update.get("message")
    if not message or message.get("text") is None:
        return None
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not chat_id:
        return None
    sender = message.get("from") or {}
    return InboundMessage(
        wa_id=chat_id,
        message_id=f"tg-{update.get('update_id', '')}",
        timestamp=int(message.get("date", 0)),
        text=message["text"],
        profile_name=sender.get("first_name"),
    )


class TelegramPoller:
    """Polls the Bot API and feeds each inbound message to a handler.

    Tracks the update offset so every update is delivered exactly once.
    """

    def __init__(
        self,
        bot,
        handler: Callable[[InboundMessage], None],
        *,
        interval: float = 1.0,
    ) -> None:
        self._bot = bot
        self._handler = handler
        self._interval = interval
        self._offset = 0

    def poll_once(self) -> int:
        """Fetch and dispatch one batch of updates; returns how many were handled."""
        handled = 0
        for update in self._bot.get_updates(self._offset, timeout=10):
            inbound = update_to_inbound(update)
            if inbound is not None:
                self._handler(inbound)
                handled += 1
            self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
        return handled

    def run_forever(self) -> None:
        while True:
            try:
                self.poll_once()
            except Exception:
                logger.exception("telegram poll failed")
            time.sleep(self._interval)
