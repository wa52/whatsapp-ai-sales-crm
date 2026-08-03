from datetime import UTC, datetime

from fakes import FakeLLM, FakeRetriever

from whatsapp_ai_sales.messaging.agent import AutoReplyAgent
from whatsapp_ai_sales.models import KnowledgeChunk, Message

SYSTEM_PROMPT = "You are a sales assistant."
FALLBACK = "I will confirm with sales and reply shortly."


def _message(role: str, content: str) -> Message:
    return Message(
        conversation_id=1,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def _chunk(content: str = "MOQ is 100 pieces.", section: str = "moq") -> KnowledgeChunk:
    return KnowledgeChunk(id=1, product_id=1, section=section, content=content)


def test_rag_reply_injects_retrieved_knowledge_into_context() -> None:
    llm = FakeLLM(content="The MOQ is 100 pieces.")
    retriever = FakeRetriever([_chunk()])
    agent = AutoReplyAgent(
        llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK, retriever=retriever
    )

    result = agent.reply([_message("inbound", "What is the MOQ?")], None)

    assert result == "The MOQ is 100 pieces."
    assert len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "MOQ is 100 pieces." in system
    assert "moq" in system


def test_rag_reply_no_match_uses_fallback_without_calling_llm() -> None:
    llm = FakeLLM(content="should not be used")
    retriever = FakeRetriever([])
    agent = AutoReplyAgent(
        llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK, retriever=retriever
    )

    result = agent.reply([_message("inbound", "unrelated small talk")], None)

    assert result == FALLBACK
    assert len(llm.calls) == 0


def test_rag_uses_last_inbound_message_as_query() -> None:
    llm = FakeLLM()
    retriever = FakeRetriever([_chunk()])
    agent = AutoReplyAgent(
        llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK, retriever=retriever
    )
    history = [
        _message("inbound", "Hello"),
        _message("outbound", "Hi!"),
        _message("inbound", "What is the MOQ?"),
    ]

    agent.reply(history, None)

    assert retriever.queries == ["What is the MOQ?"]


def test_rag_keeps_recent_turns_alongside_knowledge() -> None:
    llm = FakeLLM()
    retriever = FakeRetriever([_chunk()])
    agent = AutoReplyAgent(
        llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK, retriever=retriever
    )

    agent.reply([_message("inbound", "Price?")], None)

    contents = [m["content"] for m in llm.calls[0]]
    assert "Price?" in contents
    assert any("MOQ is 100 pieces." in m["content"] for m in llm.calls[0])


def test_rag_agent_without_retriever_preserves_v1_behavior() -> None:
    llm = FakeLLM(content="hi there")
    agent = AutoReplyAgent(llm, system_prompt=SYSTEM_PROMPT, fallback_reply=FALLBACK)

    result = agent.reply([_message("inbound", "Hello")], None)

    assert result == "hi there"
    assert len(llm.calls) == 1
