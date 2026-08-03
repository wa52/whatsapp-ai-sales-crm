"""Customer intent extraction: deterministic rules first, optional LLM structured output."""

from __future__ import annotations

import json
import re
from typing import Protocol

from pydantic import BaseModel, Field

from ..llm.base import ChatMessage
from ..models import Customer

INTENT_PRICE_INQUIRY = "price_inquiry"
INTENT_ORDER = "order"
INTENT_SAMPLE_REQUEST = "sample_request"


class CustomerIntent(BaseModel):
    """Structured intent extracted from a customer message."""

    intent_type: str | None = None
    country: str | None = None
    product: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    budget: float | None = Field(default=None, gt=0)
    purchase_time: str | None = None
    customer_type: str | None = None
    need_quote: bool = False
    need_sample: bool = False
    need_catalog: bool = False
    payment_question: bool = False
    logistics_question: bool = False
    need_human: bool = False
    price_probing: bool = False


class IntentLLM(Protocol):
    def chat(self, messages: list[ChatMessage]) -> str:
        ...


_INTENT_PROMPT = (
    "Extract customer intent from the message as JSON with exactly these keys: "
    "intent_type, country, product, quantity, budget, purchase_time, customer_type, "
    "need_quote, need_sample, need_catalog, payment_question, logistics_question, "
    "need_human, price_probing. Use booleans and numbers where applicable, null "
    "when unknown. Reply with the JSON only."
)

_QUANTITY_RE = re.compile(
    r"(\d[\d,]*)\s*(?:pcs|pieces|units|items|kg|tons|cartons|boxes|件|个|台|只)", re.IGNORECASE
)
_QUANTITY_OF_RE = re.compile(r"(?:quantity|amount|qty)[\s:]*(?:of[\s:]*)?(\d[\d,]*)", re.IGNORECASE)
_BUDGET_RE = re.compile(r"budget[^\d$]*\$?(\d[\d,]*)", re.IGNORECASE)
_TIME_RE = re.compile(r"within\s+(\d+)\s+(days|weeks|months)", re.IGNORECASE)

_QUOTE_WORDS = (
    "price", "quote", "cost", "how much", "报价", "价格", "多少钱", "preis", "prix", "precio"
)
_SAMPLE_WORDS = ("sample", "样品", "muster", "echantillon")
_CATALOG_WORDS = ("catalog", "catalogue", "brochure", "目录")
_PAYMENT_WORDS = ("payment", "pay", "tt", "paypal", "付款", "汇款", "l/c")
_LOGISTICS_WORDS = (
    "shipping", "delivery", "freight", "logistics", "运费", "物流", "运输", "versand"
)
_ORDER_WORDS = ("order", "buy", "purchase", "采购", "下单", "bestellen", "commander")
_PROBE_WORDS = ("best price", "lowest price", "cheapest", "最低价", "最便宜")
_HUMAN_WORDS = ("too expensive", "complaint", "upset", "refund", "投诉", "太贵", "不满意")


def _has_any(lowered: str, words: tuple[str, ...]) -> bool:
    return any(word in lowered for word in words)


class RuleExtractor:
    """Deterministic intent extraction from message text and customer context."""

    def __init__(self, *, product_keywords: dict[str, list[str]] | None = None) -> None:
        self._product_keywords = product_keywords or {}

    def extract(self, text: str, customer: Customer | None) -> CustomerIntent:
        lowered = text.lower()
        intent = CustomerIntent(
            country=customer.country_code if customer else None,
            need_quote=_has_any(lowered, _QUOTE_WORDS),
            need_sample=_has_any(lowered, _SAMPLE_WORDS),
            need_catalog=_has_any(lowered, _CATALOG_WORDS),
            payment_question=_has_any(lowered, _PAYMENT_WORDS),
            logistics_question=_has_any(lowered, _LOGISTICS_WORDS),
            need_human=_has_any(lowered, _HUMAN_WORDS),
            price_probing=_has_any(lowered, _PROBE_WORDS),
        )

        quantity = self._match_quantity(lowered)
        if quantity is not None:
            intent.quantity = quantity

        budget = _BUDGET_RE.search(lowered)
        if budget:
            intent.budget = float(budget.group(1).replace(",", ""))

        time_match = _TIME_RE.search(lowered)
        if time_match:
            intent.purchase_time = f"within {time_match.group(1)} {time_match.group(2)}"
        elif _has_any(lowered, ("asap", "immediately", "尽快", "立即")):
            intent.purchase_time = "immediately"
        elif "this month" in lowered or "本月" in lowered:
            intent.purchase_time = "this month"
        elif "next month" in lowered or "下月" in lowered:
            intent.purchase_time = "next month"

        customer_type = self._match_customer_type(lowered)
        if customer_type:
            intent.customer_type = customer_type

        product = self._match_product(lowered)
        if product:
            intent.product = product

        if intent.need_quote and _has_any(lowered, _ORDER_WORDS):
            intent.intent_type = INTENT_ORDER
        elif intent.need_quote:
            intent.intent_type = INTENT_PRICE_INQUIRY
        elif _has_any(lowered, _ORDER_WORDS):
            intent.intent_type = INTENT_ORDER
        elif intent.need_sample:
            intent.intent_type = INTENT_SAMPLE_REQUEST

        return intent

    @staticmethod
    def _match_quantity(lowered: str) -> int | None:
        for pattern in (_QUANTITY_OF_RE, _QUANTITY_RE):
            match = pattern.search(lowered)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    @staticmethod
    def _match_customer_type(lowered: str) -> str | None:
        for keyword, label in (
            ("distributor", "distributor"),
            ("wholesaler", "wholesaler"),
            ("retailer", "retailer"),
            ("agent", "agent"),
            ("经销商", "distributor"),
            ("批发", "wholesaler"),
        ):
            if keyword in lowered:
                return label
        return None

    def _match_product(self, lowered: str) -> str | None:
        for name, keywords in self._product_keywords.items():
            if any(k in lowered for k in keywords):
                return name
        return None


def merge_intents(base: CustomerIntent, other: CustomerIntent) -> CustomerIntent:
    """Union two extracted intents: booleans OR, scalars take the newer value."""
    merged = CustomerIntent()
    for field in CustomerIntent.model_fields:
        a = getattr(base, field)
        b = getattr(other, field)
        if isinstance(a, bool):
            setattr(merged, field, a or b)
        else:
            setattr(merged, field, b if b is not None else a)
    return merged


class IntentExtractor:
    """Extracts customer intent, preferring LLM structured output when available.

    Falls back to the deterministic rule extractor when no LLM is configured or
    the model output cannot be parsed/validated.
    """

    def __init__(
        self,
        llm_provider: IntentLLM | None = None,
        *,
        product_keywords: dict[str, list[str]] | None = None,
    ) -> None:
        self._llm = llm_provider
        self._rules = RuleExtractor(product_keywords=product_keywords)

    def extract(self, text: str, customer: Customer | None) -> CustomerIntent:
        if self._llm is not None:
            try:
                context = text
                if customer is not None and customer.country_code:
                    context += f"\nCustomer country: {customer.country_code}"
                raw = self._llm.chat(
                    [
                        {"role": "user", "content": _INTENT_PROMPT},
                        {"role": "user", "content": context},
                    ]
                )
                intent = CustomerIntent.model_validate(json.loads(raw))
                if intent.country is None and customer is not None:
                    intent.country = customer.country_code
                return intent
            except (json.JSONDecodeError, ValueError):
                pass
        return self._rules.extract(text, customer)
