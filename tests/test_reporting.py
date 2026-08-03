from datetime import UTC, datetime, timedelta

from fakes import FakeLLM
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from whatsapp_ai_sales.db import create_engine_for
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.messaging.handling import HANDLER_HUMAN
from whatsapp_ai_sales.models import ROLE_INBOUND, ROLE_OUTBOUND, Conversation, Customer, Message
from whatsapp_ai_sales.reporting import ReportService
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
FALLBACK = "SALES_FALLBACK"


def _seed(session: Session) -> None:
    old = NOW - timedelta(days=30)
    fresh = NOW - timedelta(days=1)
    a = Customer(wa_id="491111", country_code="DE", lead_level="high", lead_score=80,
                 created_at=fresh)
    b = Customer(wa_id="333111", country_code="FR", created_at=old)
    session.add_all([a, b])
    session.flush()
    conv_a = Conversation(customer_id=a.id, status="active", handler="ai", quote_sent=True)
    conv_b = Conversation(customer_id=b.id, status="active", handler=HANDLER_HUMAN)
    session.add_all([conv_a, conv_b])
    session.flush()
    session.add_all(
        [
            Message(conversation_id=conv_a.id, role=ROLE_INBOUND, content="price?"),
            Message(conversation_id=conv_a.id, role=ROLE_INBOUND, content="ok, order"),
            Message(conversation_id=conv_a.id, role=ROLE_OUTBOUND, content="8 usd"),
            Message(conversation_id=conv_b.id, role=ROLE_INBOUND, content="hello"),
            Message(conversation_id=conv_b.id, role=ROLE_OUTBOUND, content=FALLBACK),
        ]
    )
    session.commit()


def test_report_summary_computes_stats() -> None:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    _seed(session)

    summary = ReportService(session, fallback_reply=FALLBACK).summary(now=NOW)

    assert summary.total_customers == 2
    assert summary.new_customers == 1
    assert summary.high_intent == 1
    assert summary.quotes_sent == 1
    assert summary.handoffs == 1
    assert summary.reply_rate == 0.5  # one of two conversations has >= 2 inbound
    assert summary.ai_reply_success_rate == 0.5  # 1 of 2 outbound is the fallback
    assert summary.countries == {"DE": 1, "FR": 1}


def test_empty_database_summary_is_zero() -> None:
    engine = create_engine_for("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    summary = ReportService(session, fallback_reply=FALLBACK).summary(now=NOW)

    assert summary.total_customers == 0
    assert summary.reply_rate == 0.0
    assert summary.ai_reply_success_rate == 0.0
    assert summary.countries == {}


def _app() -> tuple[TestClient, MockWhatsAppProvider]:
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=FakeLLM(content="ok"), provider=provider)
    _seed(Session(app.state.engine))
    return TestClient(app), provider


def test_reports_endpoint_returns_summary() -> None:
    client, _ = _app()

    response = client.get("/api/reports/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_customers"] == 2
    assert body["high_intent"] == 1
    assert body["countries"] == {"DE": 1, "FR": 1}


def test_admin_frontend_is_served() -> None:
    client, _ = _app()

    html = client.get("/admin")
    js = client.get("/admin/app.js")

    assert html.status_code == 200
    assert "text/html" in html.headers["content-type"]
    assert "WhatsApp AI Sales" in html.text
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
