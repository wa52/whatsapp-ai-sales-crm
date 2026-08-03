"""Text chunking for building searchable knowledge slices."""

from __future__ import annotations


def chunk_text(text: str, *, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks of at most ``max_chars`` characters.

    Boundaries fall on whitespace where possible; the trailing ``overlap``
    characters of each chunk are carried into the next so no context is lost.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + 1, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
