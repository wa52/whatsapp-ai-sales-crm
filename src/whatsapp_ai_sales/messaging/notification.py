"""Sales notification events and notifier abstraction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

KIND_HANDOFF = "handoff"
KIND_LEAD_HIGH = "lead_high"


@dataclass(frozen=True)
class NotificationEvent:
    kind: str
    wa_id: str
    details: str


class Notifier(Protocol):
    def notify(self, event: NotificationEvent) -> None:
        ...


class LogNotifier:
    """Default notifier: writes events to the application log."""

    def notify(self, event: NotificationEvent) -> None:
        logger.info(
            "notification kind=%s wa_id=%s details=%s",
            event.kind,
            event.wa_id,
            event.details,
        )
