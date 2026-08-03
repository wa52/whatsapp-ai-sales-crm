"""LiteLLM-backed LLM provider implementing the LLMProvider protocol."""

from __future__ import annotations

from collections.abc import Callable

import litellm

from .base import ChatMessage


class LiteLLMProvider:
    """A unified LLM provider built on litellm.

    `model` uses litellm's ``<provider>/<model>`` notation, e.g.
    ``deepseek/deepseek-chat`` or ``openai/gpt-4o-mini``. `fallbacks` are
    alternative models tried when the primary fails.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        fallbacks: list[str] | None = None,
        on_usage: Callable[[dict], None] | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._fallbacks = fallbacks or []
        self._on_usage = on_usage

    def chat(self, messages: list[ChatMessage]) -> str:
        kwargs = {
            "model": self._model,
            "messages": messages,
            "api_key": self._api_key,
            "base_url": self._base_url,
        }
        if self._fallbacks:
            kwargs["fallbacks"] = self._fallbacks
        response = litellm.completion(**kwargs)
        if self._on_usage is not None:
            self._report_usage(response)
        return response.choices[0].message.content

    def _report_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        try:
            cost = litellm.completion_cost(response)
        except Exception:
            cost = None
        self._on_usage(
            {
                "model": self._model,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "cost": cost,
            }
        )
