from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.config import Settings
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider


def _app(token: str | None = "secret") -> TestClient:
    app = create_app(
        db_url="sqlite://",
        llm=FakeLLM(content="ok"),
        provider=MockWhatsAppProvider(),
        settings=Settings(admin_token=token),
    )
    return TestClient(app)


def test_admin_apis_reject_missing_token() -> None:
    client = _app()
    assert client.get("/api/reports/summary").status_code == 401
    assert client.get("/api/crm/conversations").status_code == 401
    assert client.get("/api/kb/products").status_code == 401


def test_admin_apis_accept_valid_token() -> None:
    client = _app()
    headers = {"X-Admin-Token": "secret"}
    assert client.get("/api/reports/summary", headers=headers).status_code == 200
    assert client.get("/api/crm/conversations", headers=headers).status_code == 200
    assert client.get("/api/kb/products", headers=headers).status_code == 200


def test_admin_apis_reject_wrong_token() -> None:
    client = _app()
    assert (
        client.get("/api/reports/summary", headers={"X-Admin-Token": "nope"}).status_code
        == 401
    )


def test_webhook_stays_public() -> None:
    client = _app()
    assert client.post("/webhooks/whatsapp", json={}).status_code == 200


def test_no_token_configured_means_open() -> None:
    client = _app(token=None)
    assert client.get("/api/reports/summary").status_code == 200
