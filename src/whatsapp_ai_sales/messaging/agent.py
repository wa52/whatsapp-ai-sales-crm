"""Auto-reply agent: assemble context, ask the LLM, and fall back safely."""

from __future__ import annotations

from ..llm.base import ChatMessage, LLMProvider
from ..models import ROLE_INBOUND, ROLE_OUTBOUND, Customer, KnowledgeChunk, Message
from ..rag.retriever import Retriever
from .language import LanguageDetector

_ROLE_MAP = {ROLE_INBOUND: "user", ROLE_OUTBOUND: "assistant"}


class AutoReplyAgent:
    """Builds a bounded prompt from recent history + customer summary and replies.

    When a retriever is configured, the latest customer question is grounded in
    retrieved product knowledge. If nothing relevant is found the agent returns
    a fixed safe message instead of letting the model guess.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        system_prompt: str,
        fallback_reply: str,
        window: int = 10,
        retriever: Retriever | None = None,
        language_detector: LanguageDetector | None = None,
    ) -> None:
        self._llm = llm_provider
        self._system_prompt = system_prompt
        self.fallback_reply = fallback_reply
        self._window = window
        self._retriever = retriever
        self._language_detector = language_detector

    def is_fallback(self, text: str) -> bool:
        """True when the agent produced its safe fallback instead of a real answer."""
        return text == self.fallback_reply

    def build_context(
        self,
        history: list[Message],
        customer: Customer | None,
        knowledge: list[KnowledgeChunk] | None = None,
        language: str | None = None,
        pricing_text: str | None = None,
    ) -> list[ChatMessage]:
        system = self._system_prompt
        if customer is not None:
            bits = []
            if customer.name:
                bits.append(f"name: {customer.name}")
            if customer.country_code:
                bits.append(f"country: {customer.country_code}")
            if bits:
                system += f"\nCustomer: {', '.join(bits)}."
        if knowledge:
            lines = "\n".join(f"- [{c.section}] {c.content}" for c in knowledge)
            system += f"\n\nProduct knowledge:\n{lines}"
        if pricing_text:
            system += f"\n\nPricing:\n{pricing_text}"
        if language:
            system += f"\nReply in language: {language}."

        turns: list[ChatMessage] = [{"role": "system", "content": system}]
        for message in _last_turns(history, self._window):
            role = _ROLE_MAP.get(message.role)
            if role is not None:
                turns.append({"role": role, "content": message.content})
        return turns

    def reply(
        self,
        history: list[Message],
        customer: Customer | None,
        *,
        pricing_text: str | None = None,
    ) -> str:
        if not history:
            return self.fallback_reply

        query = next(
            (m.content for m in reversed(history) if m.role == ROLE_INBOUND), None
        )

        language: str | None = None
        if self._language_detector is not None and query:
            language = self._language_detector.detect(query)

        knowledge: list[KnowledgeChunk] | None = None
        if self._retriever is not None:
            knowledge = self._retriever.retrieve(query) if query else []
            if not knowledge:
                return self.fallback_reply

        context = self.build_context(history, customer, knowledge, language, pricing_text)
        try:
            return self._llm.chat(context)
        except Exception:
            return self.fallback_reply


def _last_turns(history: list[Message], window: int) -> list[Message]:
    """Keep the last `window` customer turns: each inbound message plus everything
    that followed it (the assistant reply belongs to the same turn)."""
    if window <= 0:
        return []
    inbound_indexes = [i for i, m in enumerate(history) if m.role == ROLE_INBOUND]
    if len(inbound_indexes) <= window:
        return history
    start = inbound_indexes[len(inbound_indexes) - window]
    return history[start:]
