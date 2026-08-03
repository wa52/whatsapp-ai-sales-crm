"""Shared test doubles for the v1 seams."""


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


class FakeRetriever:
    def __init__(self, chunks: list) -> None:
        self.chunks = list(chunks)
        self.queries: list[str] = []

    def retrieve(self, query: str) -> list:
        self.queries.append(query)
        return list(self.chunks)
