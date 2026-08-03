from whatsapp_ai_sales.messaging.intent import CustomerIntent
from whatsapp_ai_sales.messaging.scoring import score_lead


def _intent(**kwargs) -> CustomerIntent:
    return CustomerIntent(**kwargs)


def test_bare_inquiry_is_low() -> None:
    lead = score_lead(_intent(need_quote=True))
    assert lead.score == 15  # 20 - 5 for missing qty/time/country/product
    assert lead.level == "low"
    assert "明确询价" in lead.reasons


def test_quantity_budget_time_and_logistics_push_to_high() -> None:
    intent = _intent(
        need_quote=True,
        quantity=500,
        purchase_time="this month",
        logistics_question=True,
        budget=5000,
        need_sample=True,
    )
    lead = score_lead(intent, message_count=3)

    assert lead.score == 85  # 20+15+10+10+10+10+10
    assert lead.level == "high"


def test_incomplete_info_is_penalized() -> None:
    lead = score_lead(_intent(need_quote=True))
    assert lead.score == 15  # 20 - 5 for missing qty/time/country/product
    assert "信息不完整" in lead.reasons


def test_price_probing_is_penalized() -> None:
    lead = score_lead(_intent(need_quote=True, price_probing=True))
    assert lead.score == 5  # 20 - 10 - 5
    assert "明显低价试探" in lead.reasons


def test_medium_threshold() -> None:
    lead = score_lead(_intent(need_quote=True, quantity=100, need_sample=True))
    assert lead.score == 45  # 20+15+10
    assert lead.level == "medium"


def test_score_is_clamped_to_100() -> None:
    lead = score_lead(
        _intent(need_quote=True, quantity=1, purchase_time="asap", payment_question=True,
                logistics_question=True, need_sample=True, budget=1)
    )
    assert lead.score <= 100
