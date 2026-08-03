from sqlmodel import Session, SQLModel

from whatsapp_ai_sales.db import create_engine_for
from whatsapp_ai_sales.models import PriceTier, PricingRule, Product
from whatsapp_ai_sales.pricing.service import OfferVerdict, QuoteService


def _setup() -> tuple[Session, Product, PricingRule, QuoteService]:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    product = Product(name="LED Strip", sku="LED-001")
    session.add(product)
    session.flush()
    rule = PricingRule(
        product_id=product.id,
        currency="USD",
        standard_price=10.0,
        min_price=6.0,
        auto_deal_price=6.5,
        sample_price=15.0,
    )
    session.add(rule)
    session.flush()
    session.add_all(
        [
            PriceTier(rule_id=rule.id, min_quantity=100, unit_price=8.0),
            PriceTier(rule_id=rule.id, min_quantity=500, unit_price=6.5),
        ]
    )
    session.commit()
    return session, product, rule, QuoteService(session)


def test_unit_price_hits_correct_tier() -> None:
    _, _, rule, svc = _setup()

    assert svc.unit_price_for(rule, 10) == 10.0  # below first tier -> standard
    assert svc.unit_price_for(rule, 100) == 8.0
    assert svc.unit_price_for(rule, 250) == 8.0
    assert svc.unit_price_for(rule, 500) == 6.5
    assert svc.unit_price_for(rule, None) == 10.0  # no quantity -> standard


def test_quote_computes_unit_and_total() -> None:
    _, product, _, svc = _setup()

    quote = svc.quote(product, 500)

    assert quote is not None
    assert quote.product_name == "LED Strip"
    assert quote.currency == "USD"
    assert quote.quantity == 500
    assert quote.unit_price == 6.5
    assert quote.total_price == 3250.0


def test_quote_returns_none_without_rule() -> None:
    session, _, _, svc = _setup()
    orphan = Product(name="No Pricing")
    session.add(orphan)
    session.commit()

    assert svc.quote(orphan, 10) is None


def test_evaluate_offer_accept_at_or_above_auto_deal() -> None:
    _, _, rule, svc = _setup()
    verdict: OfferVerdict = svc.evaluate_offer(rule, 6.5)
    assert verdict.action == "accept"


def test_evaluate_offer_negotiate_between_min_and_auto_deal() -> None:
    _, _, rule, svc = _setup()
    verdict: OfferVerdict = svc.evaluate_offer(rule, 6.2)
    assert verdict.action == "negotiate"


def test_evaluate_offer_human_below_min() -> None:
    _, _, rule, svc = _setup()
    verdict: OfferVerdict = svc.evaluate_offer(rule, 5.0)
    assert verdict.action == "human"


def test_offer_from_text_extracts_usd_suffix() -> None:
    svc = QuoteService.__new__(QuoteService)
    assert svc.offer_from_text("Can you do 3 USD?") == 3.0
    assert svc.offer_from_text("I will pay 4.5 dollars each") == 4.5


def test_offer_from_text_extracts_dollar_sign() -> None:
    svc = QuoteService.__new__(QuoteService)
    assert svc.offer_from_text("How about $4.5 each?") == 4.5


def test_offer_from_text_none_without_price_signal() -> None:
    svc = QuoteService.__new__(QuoteService)
    assert svc.offer_from_text("What is the price?") is None
    assert svc.offer_from_text("I need 500 pieces") is None
