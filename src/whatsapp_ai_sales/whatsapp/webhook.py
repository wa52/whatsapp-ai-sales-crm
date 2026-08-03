"""Normalization of Meta WhatsApp Cloud API webhook payloads into inbound messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    """A single inbound text message normalized from a Meta webhook payload."""

    wa_id: str
    message_id: str
    timestamp: int
    text: str
    profile_name: str | None = None


def parse_meta_payload(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extract text messages from a Meta WhatsApp Cloud API webhook payload.

    Non-text message types (image, audio, document, ...) are skipped; v1 only
    handles text. An empty or unknown payload yields no messages.
    """
    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            if value.get("messaging_product") != "whatsapp":
                continue
            contacts = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", []) or []
            }
            for raw in value.get("messages", []) or []:
                if raw.get("type") != "text":
                    continue
                text = (raw.get("text") or {}).get("body")
                if text is None:
                    continue
                wa_id = raw.get("from") or ""
                messages.append(
                    InboundMessage(
                        wa_id=wa_id,
                        message_id=raw.get("id") or "",
                        timestamp=int(raw.get("timestamp") or 0),
                        text=text,
                        profile_name=contacts.get(wa_id),
                    )
                )
    return messages
