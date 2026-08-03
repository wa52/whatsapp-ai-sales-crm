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
    """True when the AI cannot carry the conversation alone: it could not answer,
    the customer is negative/upset, or the offer fell below the floor."""
    return signals.fell_back or signals.need_human or signals.verdict_human
