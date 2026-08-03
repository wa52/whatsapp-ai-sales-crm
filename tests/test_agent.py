from datetime import UTC, datetime

from fakes import FakeLLM

from whatsapp_ai_sales.messaging.agent import AutoReplyAgent, _last_turns
from whatsapp_ai_sales.models import Customer, Message

SYSTEM_PROMPT = "You are a sales assistant."
FALLBACK = "I will confirm with sales and reply shortly."


def _message(role: str, content: str) -> Message:
    return Message(
        conversation_id=1,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_build_context_prepends_system_prompt_and_maps_roles() -> None:
    agent = AutoReplyAgent(
        FakeLLM(), system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK
    )
    history = [
        _message("inbound", "Hello"),
        _message("outbound", "Hi! How can I help?"),
        _message("inbound", "Price?"),
    ]

    context = agent.build_context(history, None)

    assert context[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert context[1:] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"},
        {"role": "user", "content": "Price?"},
    ]


def test_window_keeps_last_turns_including_assistant_replies() -> None:
    history = [
        _message("inbound", "m1"),
        _message("outbound", "r1"),
        _message("inbound", "m2"),
        _message("outbound", "r2"),
        _message("inbound", "m3"),
    ]

    # window=2 keeps the last two customer turns: m2/r2 and m3
    assert [m.content for m in _last_turns(history, 2)] == [
        "m2",
        "r2",
        "m3",
    ]

    # window=1 keeps only the last turn (m3)
    assert [m.content for m in _last_turns(history, 1)] == ["m3"]


def test_build_context_uses_window_in_turns_not_messages() -> None:
    llm = FakeLLM()
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK, window=1)
    history = [
        _message("inbound", "m1"),
        _message("outbound", "r1"),
        _message("inbound", "m2"),
        _message("outbound", "r2"),
    ]

    context = agent.build_context(history, None)

    assert context[1:] == [
        {"role": "user", "content": "m2"},
        {"role": "assistant", "content": "r2"},
    ]


def test_build_context_includes_customer_summary() -> None:
    llm = FakeLLM()
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)
    customer = Customer(wa_id="4912345678", name="Anna", country_code="DE")
    history = [_message("inbound", "Hello")]

    context = agent.build_context(history, customer)

    assert customer.name in context[0]["content"]
    assert customer.country_code in context[0]["content"]


def test_reply_returns_llm_text() -> None:
    llm = FakeLLM(content="The price is $8 each.")
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)

    result = agent.reply([_message("inbound", "Price?")], None)

    assert result == "The price is $8 each."
    assert len(llm.calls) == 1


def test_reply_returns_fallback_on_llm_error() -> None:
    llm = FakeLLM(error=RuntimeError("upstream down"))
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)

    result = agent.reply([_message("inbound", "Price?")], None)

    assert result == FALLBACK
    assert len(llm.calls) == 1


def test_reply_returns_fallback_on_empty_history() -> None:
    llm = FakeLLM(content="hello")
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)

    result = agent.reply([], None)

    assert result == FALLBACK
    assert len(llm.calls) == 0
