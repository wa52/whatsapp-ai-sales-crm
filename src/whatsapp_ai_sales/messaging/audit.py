"""Structured audit logging: append-only JSON lines for key operational events."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

AUDIT_HANDOFF = "handoff"
AUDIT_LEAD_HIGH = "lead_high"
AUDIT_TAKEOVER = "takeover"
AUDIT_RELEASE = "release"
AUDIT_MANUAL_MESSAGE = "manual_message"
AUDIT_FOLLOWUP_SENT = "followup_sent"
AUDIT_OUTBOUND_FAILED = "outbound_failed"
AUDIT_LLM_COST = "llm_cost"


class AuditLogger:
    """Writes one JSON line per event to a log file (or the app log if unset)."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path

    def log(self, kind: str, **fields) -> None:
        record = {"time": datetime.now(UTC).isoformat(), "kind": kind, **fields}
        line = json.dumps(record, ensure_ascii=False, default=str)
        if self._path:
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        else:
            logger.info("audit %s", line)
