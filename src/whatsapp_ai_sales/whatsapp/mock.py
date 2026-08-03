"""In-memory WhatsApp provider for local development and tests.

Captures every outbound message so callers can assert what was sent without
touching the real WhatsApp API.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    to: str
    text: str


class MockWhatsAppProvider:
    """A no-op provider that records sent messages in memory."""

    _ids = itertools.count(1)

    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    def send_message(self, to: str, text: str) -> str:
        message = SentMessage(message_id=f"mock.{next(self._ids)}", to=to, text=text)
        self.sent.append(message)
        return message.message_id
