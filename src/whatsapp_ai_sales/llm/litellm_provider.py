"""LiteLLM-backed LLM provider implementing the LLMProvider protocol."""

from __future__ import annotations

import litellm

from .base import ChatMessage


class LiteLLMProvider:
    """A unified LLM provider built on litellm.

    `model` uses litellm's `<provider>/<model>` notation, e.g.
    ``deepseek/deepseek-chat`` or ``openai/gpt-4o-mini``.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url

    def chat(self, messages: list[ChatMessage]) -> str:
        response = litellm.completion(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        return response.choices[0].message.content
