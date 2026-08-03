"""Unified LLM adapter: a thin seam in front of any model provider."""

from __future__ import annotations

from typing import Protocol

ChatMessage = dict[str, str]


class LLMProvider(Protocol):
    """A chat-capable language model. `messages` uses the OpenAI chat shape."""

    def chat(self, messages: list[ChatMessage]) -> str:
        """Return the model's reply text for the given message history."""
        ...
