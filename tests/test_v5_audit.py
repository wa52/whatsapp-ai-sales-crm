import json
from types import SimpleNamespace

import pytest

from whatsapp_ai_sales.llm.litellm_provider import LiteLLMProvider
from whatsapp_ai_sales.messaging.audit import AuditLogger


def _response(content: str = "ok", usage: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(**(usage or {"prompt_tokens": 10, "completion_tokens": 5})),
    )


def test_provider_passes_fallbacks_to_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _response()

    monkeypatch.setattr("litellm.completion", fake_completion)

    provider = LiteLLMProvider(
        model="deepseek/deepseek-chat", fallbacks=["openai/gpt-4o-mini"]
    )
    provider.chat([{"role": "user", "content": "hi"}])

    assert captured["fallbacks"] == ["openai/gpt-4o-mini"]


def test_provider_no_fallbacks_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _response()

    monkeypatch.setattr("litellm.completion", fake_completion)

    LiteLLMProvider(model="deepseek/deepseek-chat").chat([{"role": "user", "content": "hi"}])

    assert "fallbacks" not in captured


def test_provider_reports_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_completion(**kwargs):
        return _response(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setattr("litellm.completion_cost", lambda response: 0.001)

    reports: list[dict] = []
    provider = LiteLLMProvider(model="deepseek/deepseek-chat", on_usage=reports.append)
    provider.chat([{"role": "user", "content": "hi"}])

    assert reports[0]["prompt_tokens"] == 10
    assert reports[0]["completion_tokens"] == 5
    assert reports[0]["total_tokens"] == 15
    assert reports[0]["cost"] == 0.001


def test_audit_logger_writes_json_lines(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLogger(path=str(path))

    audit.log("handoff", wa_id="4912345678", reason="fallback")
    audit.log("lead_high", wa_id="1", score=80)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "handoff"
    assert first["wa_id"] == "4912345678"
