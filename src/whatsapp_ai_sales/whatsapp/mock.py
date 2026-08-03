"""In-memory WhatsApp provider for local development and tests.

Captures every outbound message so callers can assert what was sent without
touching the real WhatsApp API.
"""

from __future__ import annotations

import itertools


class MockWhatsAppProvider:
    """A no-op provider that records sent messages in memory."""

    _ids = itertools.count(1)

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []  # (message_id, to, text)

    def send_message(self, to: str, text: str) -> str:
        message_id = f"mock.{next(self._ids)}"
        self.sent.append((message_id, to, text))
        return message_id
