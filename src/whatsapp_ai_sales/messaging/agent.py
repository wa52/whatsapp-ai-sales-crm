"""Auto-reply agent: assemble context, ask the LLM, and fall back safely."""

from __future__ import annotations

from ..llm.base import ChatMessage, LLMProvider
from ..models import Customer, Message

_ROLE_MAP = {"inbound": "user", "outbound": "assistant"}


class AutoReplyAgent:
    """Builds a bounded prompt from recent history + customer summary and replies.

    The LLM only formats the reply; anything the agent cannot answer falls back
    to a fixed safe message instead of letting the model guess.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        system_prompt: str,
        fallback_reply: str,
        window: int = 10,
    ) -> None:
        self._llm = llm_provider
        self._system_prompt = system_prompt
        self._fallback_reply = fallback_reply
        self._window = window

    def build_context(
        self, history: list[Message], customer: Customer | None
    ) -> list[ChatMessage]:
        summary = ""
        if customer is not None:
            bits = []
            if customer.name:
                bits.append(f"name: {customer.name}")
            if customer.country_code:
                bits.append(f"country: {customer.country_code}")
            if bits:
                summary = f"\nCustomer: {', '.join(bits)}."
        system = f"{self._system_prompt}{summary}"

        turns: list[ChatMessage] = [{"role": "system", "content": system}]
        for message in _last_turns(history, self._window):
            role = _ROLE_MAP.get(message.role)
            if role is not None:
                turns.append({"role": role, "content": message.content})
        return turns

    def reply(self, history: list[Message], customer: Customer | None) -> str:
        if not history:
            return self._fallback_reply
        context = self.build_context(history, customer)
        try:
            return self._llm.chat(context)
        except Exception:
            return self._fallback_reply


def _last_turns(history: list[Message], window: int) -> list[Message]:
    """Keep the last `window` customer turns: each inbound message plus everything
    that followed it (the assistant reply belongs to the same turn)."""
    if window <= 0:
        return []
    inbound_indexes = [i for i, m in enumerate(history) if m.role == "inbound"]
    if len(inbound_indexes) <= window:
        return history
    start = inbound_indexes[len(inbound_indexes) - window]
    return history[start:]
