from types import SimpleNamespace

import pytest

from whatsapp_ai_sales.llm.litellm_provider import LiteLLMProvider


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_chat_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return _response("The price is $8.00 each.")

    monkeypatch.setattr("litellm.completion", fake_completion)

    provider = LiteLLMProvider(model="deepseek/deepseek-chat")
    result = provider.chat([{"role": "user", "content": "What is the price?"}])

    assert result == "The price is $8.00 each."
    assert calls[0]["model"] == "deepseek/deepseek-chat"
    assert calls[0]["messages"] == [{"role": "user", "content": "What is the price?"}]


def test_chat_passes_api_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return _response("ok")

    monkeypatch.setattr("litellm.completion", fake_completion)

    provider = LiteLLMProvider(
        model="openai/gpt-4o-mini",
        api_key="sk-test",
        base_url="https://proxy.example.com/v1",
    )
    provider.chat([{"role": "user", "content": "hi"}])

    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://proxy.example.com/v1"


def test_chat_raises_when_completion_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_completion(**kwargs: object) -> dict:
        raise RuntimeError("upstream down")

    monkeypatch.setattr("litellm.completion", fake_completion)

    provider = LiteLLMProvider(model="deepseek/deepseek-chat")
    with pytest.raises(RuntimeError, match="upstream down"):
        provider.chat([{"role": "user", "content": "hi"}])
