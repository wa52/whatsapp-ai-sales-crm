"""Conversation handoff policy: when the AI should yield to a human."""

from __future__ import annotations

from dataclasses import dataclass

HANDLER_AI = "ai"
HANDLER_HUMAN = "human"


@dataclass(frozen=True)
class HandoffSignals:
    """Signals that decide whether a conversation should be handed to a human."""

    fell_back: bool = False
    need_human: bool = False
    verdict_human: bool = False


def should_handoff(signals: HandoffSignals) -> bool:
    """True when a human must take over: a negative/upset customer or an offer
    below the floor. An unanswered question (fallback) alone no longer hands the
    conversation over — the AI keeps answering and sales is notified instead."""
    return signals.need_human or signals.verdict_human
