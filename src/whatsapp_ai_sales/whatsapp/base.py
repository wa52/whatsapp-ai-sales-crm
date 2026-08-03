"""WhatsApp provider seam: send messages out on a WhatsApp channel."""

from __future__ import annotations

from typing import Protocol


class WhatsAppProvider(Protocol):
    """Sends outbound messages and returns a provider message id."""

    def send_message(self, to: str, text: str) -> str:
        ...
