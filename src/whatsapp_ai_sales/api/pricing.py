"""Pricing rule admin APIs: the program-authoritative source of prices."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..deps import SessionDep
from ..models import PriceTier, PricingRule
from ..pricing.service import QuoteService

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


class TierIn(BaseModel):
    min_quantity: int
    unit_price: float


class TierOut(BaseModel):
    min_quantity: int
    unit_price: float


class RuleIn(BaseModel):
    currency: str = "USD"
    standard_price: float
    min_price: float
    auto_deal_price: float
    sample_price: float | None = None
    discount_allowed: bool = True
    tiers: list[TierIn] = []


class RuleOut(BaseModel):
    product_id: int
    currency: str
    standard_price: float
    min_price: float
    auto_deal_price: float
    sample_price: float | None = None
    discount_allowed: bool
    tiers: list[TierOut]


@router.post("/products/{product_id}/rule", response_model=RuleOut)
def upsert_rule(product_id: int, payload: RuleIn, session: SessionDep) -> RuleOut:
    service = QuoteService(session)
    service.set_rule(
        product_id,
        currency=payload.currency,
        standard_price=payload.standard_price,
        min_price=payload.min_price,
        auto_deal_price=payload.auto_deal_price,
        sample_price=payload.sample_price,
        discount_allowed=payload.discount_allowed,
        tiers=[PriceTier(**tier.model_dump()) for tier in payload.tiers],
    )
    rule = service.get_rule(product_id)
    return _rule_out(session, rule)


@router.get("/products/{product_id}/rule", response_model=RuleOut)
def get_rule(product_id: int, session: SessionDep) -> RuleOut:
    rule = QuoteService(session).get_rule(product_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    return _rule_out(session, rule)


def _rule_out(session: Session, rule: PricingRule) -> RuleOut:
    tiers = session.exec(
        select(PriceTier).where(PriceTier.rule_id == rule.id).order_by(PriceTier.min_quantity)
    ).all()
    return RuleOut(
        product_id=rule.product_id,
        currency=rule.currency,
        standard_price=rule.standard_price,
        min_price=rule.min_price,
        auto_deal_price=rule.auto_deal_price,
        sample_price=rule.sample_price,
        discount_allowed=rule.discount_allowed,
        tiers=[TierOut(min_quantity=t.min_quantity, unit_price=t.unit_price) for t in tiers],
    )
