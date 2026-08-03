from datetime import UTC, datetime

from fakes import FakeLLM
from fastapi.testclient import TestClient

from whatsapp_ai_sales.main import create_app
from whatsapp_ai_sales.messaging.agent import AutoReplyAgent
from whatsapp_ai_sales.models import Message
from whatsapp_ai_sales.whatsapp.mock import MockWhatsAppProvider

SYSTEM_PROMPT = "You are a sales assistant."
FALLBACK = "I will confirm with sales and reply shortly."


def _message(role: str, content: str) -> Message:
    return Message(
        conversation_id=1,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


class FakeDetector:
    def __init__(self, language: str | None) -> None:
        self._language = language
        self.queries: list[str] = []

    def detect(self, text: str) -> str | None:
        self.queries.append(text)
        return self._language


def test_language_instruction_appended_to_system_prompt() -> None:
    llm = FakeLLM(content="Hallo! Der Preis ist 8 USD pro Stück.")
    detector = FakeDetector("de")
    agent = AutoReplyAgent(
        llm,
        system_prompt=SYSTEM_PROMPT,
        fallback_reply=FALLBACK,
        language_detector=detector,
    )

    result = agent.reply([_message("inbound", "Hallo, wie ist der Preis?")], None)

    assert result == "Hallo! Der Preis ist 8 USD pro Stück."
    system = llm.calls[0][0]["content"]
    assert "Reply in language: de." in system


def test_language_detector_uses_last_inbound_message() -> None:
    llm = FakeLLM()
    detector = FakeDetector("fr")
    agent = AutoReplyAgent(
        llm,
        system_prompt=SYSTEM_PROMPT,
        fallback_reply=FALLBACK,
        language_detector=detector,
    )
    history = [
        _message("inbound", "Hello"),
        _message("outbound", "Hi!"),
        _message("inbound", "Bonjour, quel est le prix?"),
    ]

    agent.reply(history, None)

    assert detector.queries == ["Bonjour, quel est le prix?"]


def test_no_instruction_when_detection_returns_none() -> None:
    llm = FakeLLM(content="ok")
    agent = AutoReplyAgent(
        llm,
        system_prompt=SYSTEM_PROMPT,
        fallback_reply=FALLBACK,
        language_detector=FakeDetector(None),
    )

    agent.reply([_message("inbound", "hello")], None)

    system = llm.calls[0][0]["content"]
    assert "Reply in language" not in system


def test_no_instruction_without_detector() -> None:
    llm = FakeLLM(content="ok")
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)

    agent.reply([_message("inbound", "hello")], None)

    system = llm.calls[0][0]["content"]
    assert "Reply in language" not in system


META_FR = {
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
                        "contacts": [{"profile": {"name": "Jean"}, "wa_id": "33612345678"}],
                        "messages": [
                            {
                                "from": "33612345678",
                                "id": "wamid.FR",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "Bonjour, quel est le prix?"},
                            }
                        ],
                    }
                }
            ],
        }
    ],
}


def test_integration_french_message_gets_language_instruction() -> None:
    llm = FakeLLM(content="Le prix est de 5 USD.")
    provider = MockWhatsAppProvider()
    app = create_app(db_url="sqlite://", llm=llm, provider=provider)
    client = TestClient(app)
    client.post(
        "/api/kb/products",
        json={"name": "Widget", "sections": {"faq": "Le prix est de 5 USD."}},
    )

    response = client.post("/webhooks/whatsapp", json=META_FR)

    assert response.status_code == 200
    assert len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "Reply in language: fr." in system
    assert provider.sent[0].text == "Le prix est de 5 USD."
