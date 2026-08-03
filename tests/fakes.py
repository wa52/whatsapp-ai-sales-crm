"""Shared test doubles for the v1 seams."""

import json


class FakeLLM:
    def __init__(self, *, content: str = "ok", error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if self._error is not None:
            raise self._error
        return self._content


class RecordingNotifier:
    def __init__(self) -> None:
        self.events: list = []

    def notify(self, event) -> None:
        self.events.append(event)


class ConditionalLLM:
    """Returns a canned JSON payload for intent-extraction prompts, a plain
    reply otherwise. Lets one instance play both the reply and the extractor."""

    def __init__(self, *, reply: str = "ok", json_payload: dict | None = None) -> None:
        self._reply = reply
        self._json_payload = json_payload or {}
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if any("Extract customer intent" in m.get("content", "") for m in messages):
            return json.dumps(self._json_payload)
        return self._reply


class FakeRetriever:
    def __init__(self, chunks: list) -> None:
        self.chunks = list(chunks)
        self.queries: list[str] = []

    def retrieve(self, query: str) -> list:
        self.queries.append(query)
        return list(self.chunks)
