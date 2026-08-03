"""Program-computed pricing and offer evaluation. The LLM never computes prices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session, select

from ..models import PriceTier, PricingRule, Product

_OFFER_DOLLAR_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_OFFER_SUFFIX_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:usd|dollars|us dollars)", re.IGNORECASE)


@dataclass(frozen=True)
class PriceQuote:
    product_name: str
    currency: str
    quantity: int | None
    unit_price: float
    total_price: float


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
        total = unit_price * quantity if quantity else unit_price
        return PriceQuote(
            product_name=product.name,
            currency=rule.currency,
            quantity=quantity,
            unit_price=unit_price,
            total_price=round(total, 2),
        )

    def evaluate_offer(self, rule: PricingRule, offer_unit_price: float) -> OfferVerdict:
        if offer_unit_price >= rule.auto_deal_price:
            return OfferVerdict(
                action="accept",
                guidance=(
                    f"The offer of {offer_unit_price:.2f} {rule.currency} is acceptable; "
                    "the AI may confirm the deal."
                ),
            )
        if offer_unit_price >= rule.min_price:
            return OfferVerdict(
                action="negotiate",
                guidance=(
                    f"The offer of {offer_unit_price:.2f} {rule.currency} is between the "
                    f"minimum ({rule.min_price:.2f}) and the auto-deal price "
                    f"({rule.auto_deal_price:.2f}); negotiate carefully or involve sales."
                ),
            )
        return OfferVerdict(
            action="human",
            guidance=(
                f"The offer of {offer_unit_price:.2f} {rule.currency} is below the minimum "
                "acceptable price; do not accept, route to a salesperson."
            ),
        )

    @staticmethod
    def offer_from_text(text: str) -> float | None:
        """Extract a customer's unit-price offer (``$4.5`` or ``4.5 USD``) or None."""
        match = _OFFER_SUFFIX_RE.search(text)
        if match:
            return float(match.group(1))
        match = _OFFER_DOLLAR_RE.search(text)
        if match:
            return float(match.group(1))
        return None
