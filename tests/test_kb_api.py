from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.config import Settings
from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

META = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA_ID",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15551234567",
                            "phone_number_id": "PHONE_NUMBER_ID",
                        },
                        "contacts": [{"profile": {"name": "John Doe"}, "wa_id": "4912345678"}],
                        "messages": [
                            {
                                "from": "4912345678",
                                "id": "wamid.ABC",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "What is the MOQ?"},
                            }
                        ],
                    }
                }
            ],
        }
    ],
}


def _app() -> tuple[TestClient, FakeLLM, MockWhatsAppProvider, Settings]:
    llm = FakeLLM(content="The MOQ is 100 pieces.")
    provider = MockWhatsAppProvider()
    settings = Settings(fallback_reply="SALES_FALLBACK")
    app = create_app(db_url="sqlite://", llm=llm, provider=provider, settings=settings)
    return TestClient(app), llm, provider, settings


def _add_product(client: TestClient, name: str = "LED Strip", sections: dict | None = None) -> int:
    sections = sections or {"moq": "MOQ is 100 pieces, lead time 15 days."}
    response = client.post("/api/kb/products", json={"name": name, "sections": sections})
    assert response.status_code == 200
    return response.json()["id"]


def test_kb_create_and_list_product() -> None:
    client, _, _, _ = _app()
    product_id = _add_product(client)

    rows = client.get("/api/kb/products").json()

    assert [r["id"] for r in rows] == [product_id]
    assert rows[0]["name"] == "LED Strip"


def test_kb_delete_product_removes_it() -> None:
    client, _, _, _ = _app()
    product_id = _add_product(client)

    response = client.delete(f"/api/kb/products/{product_id}")

    assert response.json() == {"status": "ok"}
    assert client.get("/api/kb/products").json() == []


def test_kb_upsert_same_name_replaces_chunks() -> None:
    client, _, _, _ = _app()
    _add_product(client, "LED Strip", {"moq": "MOQ is 100 pieces."})

    client.post(
        "/api/kb/products", json={"name": "LED Strip", "sections": {"moq": "MOQ is 200 pieces."}}
    )

    rows = client.get("/api/kb/products").json()
    assert len(rows) == 1


def test_rag_reply_is_grounded_in_product_knowledge() -> None:
    client, llm, provider, _ = _app()
    _add_product(client)

    response = client.post("/webhooks/whatsapp", json=META)

    assert response.status_code == 200
    assert len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "MOQ is 100 pieces" in system
    assert provider.sent[0].text == "The MOQ is 100 pieces."


def test_rag_reply_falls_back_without_knowledge() -> None:
    client, llm, provider, settings = _app()

    client.post("/webhooks/whatsapp", json=META)

    assert len(llm.calls) == 0
    assert provider.sent[0].text == settings.fallback_reply


def test_rag_reply_falls_back_when_query_is_unrelated() -> None:
    client, llm, provider, settings = _app()
    _add_product(client)

    unrelated = {
        **META,
        "entry": [
            {
                **META["entry"][0],
                "changes": [
                    {
                        **META["entry"][0]["changes"][0],
                        "value": {
                            **META["entry"][0]["changes"][0]["value"],
                            "messages": [
                                {
                                    "from": "4912345678",
                                    "id": "wamid.UNREL",
                                    "timestamp": "1700000001",
                                    "type": "text",
                                    "text": {"body": "How is the weather today?"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    client.post("/webhooks/whatsapp", json=unrelated)

    assert len(llm.calls) == 0
    assert provider.sent[0].text == settings.fallback_reply


def test_rag_reply_falls_back_after_product_deleted() -> None:
    client, llm, provider, settings = _app()
    product_id = _add_product(client)
    client.delete(f"/api/kb/products/{product_id}")

    client.post("/webhooks/whatsapp", json=META)

    assert len(llm.calls) == 0
    assert provider.sent[0].text == settings.fallback_reply


def test_reindex_endpoint_succeeds() -> None:
    client, _, _, _ = _app()
    _add_product(client)

    response = client.post("/api/kb/reindex")

    assert response.json() == {"status": "ok"}
    # after reindex the knowledge is still retrievable
    client.post("/webhooks/whatsapp", json=META)
