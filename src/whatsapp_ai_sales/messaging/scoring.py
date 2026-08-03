"""Rule-based lead scoring for customer intents."""

from __future__ import annotations

from dataclasses import dataclass

from .intent import CustomerIntent

HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40


@dataclass(frozen=True)
class LeadScore:
    score: int
    level: str
    reasons: tuple[str, ...]


def score_lead(intent: CustomerIntent, *, message_count: int = 0) -> LeadScore:
    """Score an extracted intent 0-100 and classify high/medium/low.

    Deterministic table-based scoring so the same customer always gets the same
    score. Thresholds: high >= 70, medium >= 40, low < 40.
    """
    score = 0
    reasons: list[str] = []

    is_inquiry = intent.need_quote or intent.intent_type in ("price_inquiry", "order")
    if is_inquiry:
        score += 20
        reasons.append("明确询价")
    if intent.quantity:
        score += 15
        reasons.append("提供采购数量")
    if intent.purchase_time:
        score += 10
        reasons.append("提供采购时间")
    if intent.payment_question or intent.logistics_question:
        score += 10
        reasons.append("询问付款/物流")
    if intent.need_sample:
        score += 10
        reasons.append("要求样品")
    if intent.budget:
        score += 10
        reasons.append("提供预算")
    if message_count >= 3:
        score += 10
        reasons.append("多次回复")

    if intent.price_probing:
        score -= 10
        reasons.append("明显低价试探")

    if score > 0 and not intent.quantity and not intent.purchase_time:
        score -= 5
        reasons.append("信息不完整")

    score = max(0, min(100, score))
    if score >= HIGH_THRESHOLD:
        level = "high"
    elif score >= MEDIUM_THRESHOLD:
        level = "medium"
    else:
        level = "low"
    return LeadScore(score=score, level=level, reasons=tuple(reasons))
