"""Program-computed pricing and offer evaluation. The LLM never computes prices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session, select

from ..models import PriceTier, PricingRule, Product

ACTION_ACCEPT = "accept"
ACTION_NEGOTIATE = "negotiate"
ACTION_HUMAN = "human"

_OFFER_SUFFIX_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:usd|dollars|us dollars)", re.IGNORECASE)
_OFFER_DOLLAR_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_OFFER_SIGNAL_RE = re.compile(
    r"can you do|how about|i'?ll pay|will pay|we can pay|can pay|offer|give (?:me|us)"
    r"|price of|per unit|each",
    re.IGNORECASE,
)
_FORBIDDEN_RE = re.compile(r"budget|total|moq|minimum", re.IGNORECASE)


@dataclass(frozen=True)
class PriceQuote:
    product_name: str
    currency: str
    quantity: int | None
    unit_price: float
    total_price: float | None


@dataclass(frozen=True)
class OfferVerdict:
    action: Literal["accept", "negotiate", "human"]
    guidance: str


class QuoteService:
    """Computes prices and evaluates customer offers against a product's rule."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_rule(self, product_id: int) -> PricingRule | None:
        return self._session.exec(
            select(PricingRule).where(PricingRule.product_id == product_id)
        ).first()

    def set_rule(
        self,
        product_id: int,
        *,
        currency: str = "USD",
        standard_price: float,
        min_price: float,
        auto_deal_price: float,
        sample_price: float | None = None,
        discount_allowed: bool = True,
        tiers: list[PriceTier] | None = None,
    ) -> PricingRule:
        rule = self.get_rule(product_id)
        if rule is None:
            rule = PricingRule(product_id=product_id)
            self._session.add(rule)
        rule.currency = currency
        rule.standard_price = standard_price
        rule.min_price = min_price
        rule.auto_deal_price = auto_deal_price
        rule.sample_price = sample_price
        rule.discount_allowed = discount_allowed
        self._session.flush()

        for old in self._session.exec(
            select(PriceTier).where(PriceTier.rule_id == rule.id)
        ).all():
            self._session.delete(old)
        self._session.flush()
        for tier in tiers or []:
            self._session.add(
                PriceTier(rule_id=rule.id, **tier.model_dump())
            )
        self._session.commit()
        return rule

    def unit_price_for(self, rule: PricingRule, quantity: int | None) -> float:
        if quantity is None:
            return rule.standard_price
        tiers = self._session.exec(
            select(PriceTier)
            .where(PriceTier.rule_id == rule.id)
            .order_by(PriceTier.min_quantity)
        ).all()
        best: PriceTier | None = None
        for tier in tiers:
            if tier.min_quantity <= quantity:
                best = tier
        return best.unit_price if best is not None else rule.standard_price

    def quote(self, product: Product, quantity: int | None) -> PriceQuote | None:
        rule = self.get_rule(product.id)
        if rule is None:
            return None
        unit_price = self.unit_price_for(rule, quantity)
        total = round(unit_price * quantity, 2) if quantity else None
        return PriceQuote(
            product_name=product.name,
            currency=rule.currency,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total,
        )

    def evaluate_offer(self, rule: PricingRule, offer_unit_price: float) -> OfferVerdict:
        if offer_unit_price >= rule.auto_deal_price:
            return OfferVerdict(
                action=ACTION_ACCEPT,
                guidance=(
                    f"The offer of {offer_unit_price:.2f} {rule.currency} is acceptable; "
                    "the AI may confirm the deal."
                ),
            )
        if offer_unit_price >= rule.min_price:
            return OfferVerdict(
                action=ACTION_NEGOTIATE,
                guidance=(
                    f"The offer of {offer_unit_price:.2f} {rule.currency} is between the "
                    f"minimum ({rule.min_price:.2f}) and the auto-deal price "
                    f"({rule.auto_deal_price:.2f}); negotiate carefully or involve sales."
                ),
            )
        return OfferVerdict(
            action=ACTION_HUMAN,
            guidance=(
                f"The offer of {offer_unit_price:.2f} {rule.currency} is below the minimum "
                "acceptable price; do not accept, route to a salesperson."
            ),
        )


def extract_offer(text: str) -> float | None:
    """Extract a customer's unit-price offer (``$4.5`` or ``4.5 USD``) or None.

    A number is only treated as an offer when it appears in an offer-like
    context (``can you do``, ``pay``, ``how about``, ...) and is not part of a
    budget/total statement, so "budget is 5000 USD" is not an offer.
    """
    for match in _OFFER_SUFFIX_RE.finditer(text):
        if _is_offer(text, match.start()):
            return float(match.group(1))
    for match in _OFFER_DOLLAR_RE.finditer(text):
        if _is_offer(text, match.start()):
            return float(match.group(1))
    return None


def _is_offer(text: str, position: int) -> bool:
    if _FORBIDDEN_RE.search(text[max(0, position - 30) : position]):
        return False
    return bool(_OFFER_SIGNAL_RE.search(text))
