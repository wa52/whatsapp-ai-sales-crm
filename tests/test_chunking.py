from whatsapp_ai_sales.rag.chunking import chunk_text


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Hello world") == ["Hello world"]


def test_empty_and_blank_text_yield_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_long_text_splits_into_bounded_chunks() -> None:
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, max_chars=120, overlap=20)

    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)
    assert "".join(chunks).replace(" ", "").count("word") >= 100


def test_chunks_overlap_on_boundaries() -> None:
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, max_chars=120, overlap=20)

    for earlier, later in zip(chunks, chunks[1:], strict=False):
        tail = set(earlier.split()[-4:])
        assert tail & set(later.split()), f"no overlap between {earlier!r} and {later!r}"
