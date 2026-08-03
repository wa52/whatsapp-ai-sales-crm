import pytest
from fakes import FakeLLM
from pydantic import ValidationError

from whatsapp_ai_sales.messaging.intent import CustomerIntent, IntentExtractor, RuleExtractor
from whatsapp_ai_sales.models import Customer


def _customer(country: str = "DE") -> Customer:
    return Customer(wa_id="4912345678", country_code=country)


class TestCustomerIntentValidation:
    def test_defaults(self) -> None:
        intent = CustomerIntent()
        assert intent.need_quote is False
        assert intent.quantity is None
        assert intent.country is None

    def test_quantity_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            CustomerIntent(quantity=0)

    def test_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            CustomerIntent(budget=-1)


class TestRuleExtractor:
    def test_extracts_quantity_from_pieces(self) -> None:
        intent = RuleExtractor().extract("I need 500 pieces shipped to Germany", _customer())
        assert intent.quantity == 500

    def test_extracts_quantity_from_quantity_of(self) -> None:
        intent = RuleExtractor().extract("quantity of 1200", _customer())
        assert intent.quantity == 1200

    def test_quote_and_catalog_flags(self) -> None:
        intent = RuleExtractor().extract("What is the price? Send a quote and catalog", _customer())
        assert intent.need_quote is True
        assert intent.need_catalog is True

    def test_sample_flag(self) -> None:
        intent = RuleExtractor().extract("Can I get a free sample?", _customer())
        assert intent.need_sample is True

    def test_payment_and_logistics_flags(self) -> None:
        intent = RuleExtractor().extract(
            "Do you support PayPal payment? What is the shipping cost?", _customer()
        )
        assert intent.payment_question is True
        assert intent.logistics_question is True

    def test_uses_customer_country(self) -> None:
        intent = RuleExtractor().extract("How much?", _customer())
        assert intent.country == "DE"

    def test_extracts_purchase_time(self) -> None:
        intent = RuleExtractor().extract("I want to order within 2 weeks", _customer())
        assert intent.purchase_time == "within 2 weeks"

    def test_extracts_budget(self) -> None:
        intent = RuleExtractor().extract("My budget is around 5000 usd", _customer())
        assert intent.budget == 5000.0

    def test_extracts_customer_type(self) -> None:
        intent = RuleExtractor().extract("We are a distributor in Europe", _customer())
        assert intent.customer_type == "distributor"

    def test_classifies_price_inquiry_intent(self) -> None:
        intent = RuleExtractor().extract("How much for the LED strip?", _customer())
        assert intent.intent_type == "price_inquiry"

    def test_classifies_order_intent(self) -> None:
        intent = RuleExtractor().extract("I want to place an order", _customer())
        assert intent.intent_type == "order"

    def test_price_probing_flag(self) -> None:
        intent = RuleExtractor().extract("What is your best price? cheapest?", _customer())
        assert intent.price_probing is True

    def test_empty_text_yields_defaults(self) -> None:
        intent = RuleExtractor().extract("", _customer())
        assert intent.quantity is None
        assert intent.need_quote is False


class TestIntentExtractor:
    def test_uses_llm_json_when_valid(self) -> None:
        llm = FakeLLM(
            content='{"quantity": 999, "need_quote": true, "country": "FR", "product": "LED Strip"}'
        )
        extractor = IntentExtractor(llm)

        intent = extractor.extract("ignored", _customer())

        assert intent.quantity == 999
        assert intent.need_quote is True
        assert intent.country == "FR"

    def test_falls_back_to_rules_on_invalid_llm_output(self) -> None:
        llm = FakeLLM(content="sorry, not json")
        extractor = IntentExtractor(llm)

        intent = extractor.extract("I need 200 pieces, what is the price?", _customer())

        assert intent.quantity == 200
        assert intent.need_quote is True

    def test_rules_only_without_llm(self) -> None:
        extractor = IntentExtractor()

        intent = extractor.extract("I need 200 pieces", _customer())

        assert intent.quantity == 200
