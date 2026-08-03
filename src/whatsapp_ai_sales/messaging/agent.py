"""Auto-reply agent: assemble context, ask the LLM, and fall back safely."""

from __future__ import annotations

from ..llm.base import ChatMessage, LLMProvider
from ..models import ROLE_INBOUND, Customer, KnowledgeChunk, Message
from ..rag.retriever import Retriever

_ROLE_MAP = {ROLE_INBOUND: "user", "outbound": "assistant"}


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
    ) -> None:
        self._llm = llm_provider
        self._system_prompt = system_prompt
        self._fallback_reply = fallback_reply
        self._window = window
        self._retriever = retriever

    def build_context(
        self,
        history: list[Message],
        customer: Customer | None,
        knowledge: list[KnowledgeChunk] | None = None,
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

        turns: list[ChatMessage] = [{"role": "system", "content": system}]
        for message in _last_turns(history, self._window):
            role = _ROLE_MAP.get(message.role)
            if role is not None:
                turns.append({"role": role, "content": message.content})
        return turns

    def reply(self, history: list[Message], customer: Customer | None) -> str:
        if not history:
            return self._fallback_reply

        knowledge: list[KnowledgeChunk] | None = None
        if self._retriever is not None:
            query = next(
                (m.content for m in reversed(history) if m.role == ROLE_INBOUND), None
            )
            knowledge = self._retriever.retrieve(query) if query else []
            if not knowledge:
                return self._fallback_reply

        context = self.build_context(history, customer, knowledge)
        try:
            return self._llm.chat(context)
        except Exception:
            return self._fallback_reply


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
