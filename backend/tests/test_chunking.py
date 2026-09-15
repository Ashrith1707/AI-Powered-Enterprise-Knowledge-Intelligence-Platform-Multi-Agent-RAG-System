"""Chunking unit tests — page mapping, overlap, oversized content."""
from __future__ import annotations

from app.services.chunking import chunk_pages
from app.services.parsing import PageText


def _page(n: int, text: str) -> PageText:
    return PageText(number=n, text=text)


def test_single_page_short_text_is_one_chunk():
    chunks = chunk_pages([_page(1, "Short sentence. Another one.")], chunk_size=1000, chunk_overlap=200)
    assert len(chunks) == 1
    assert chunks[0].page_start == 1 and chunks[0].page_end == 1


def test_chunk_respects_size_and_overlap():
    sentences = [f"Sentence number {i} talks about topic {i % 7} in some detail." for i in range(60)]
    text = " ".join(sentences)
    chunks = chunk_pages([_page(1, text)], chunk_size=400, chunk_overlap=80)
    assert len(chunks) > 3
    for c in chunks:
        assert c.char_count <= 400 + 120  # size + one sentence overshoot tolerance
    # overlap: tail of chunk N appears in chunk N+1
    tail = chunks[0].content.split()[-4:]
    assert " ".join(tail) in chunks[1].content


def test_page_mapping_is_preserved():
    pages = [
        _page(1, "First page content. " * 30),
        _page(2, "Second page content. " * 30),
        _page(3, "Third page content. " * 30),
    ]
    chunks = chunk_pages(pages, chunk_size=300, chunk_overlap=50)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3
    page_numbers = {(c.page_start, c.page_end) for c in chunks}
    assert any(p[0] >= 2 for p in page_numbers)


def test_oversized_sentence_hard_split():
    giant = "word " * 2000  # single 10k-char "sentence" without punctuation
    chunks = chunk_pages([_page(1, giant.strip())], chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 5
    for c in chunks:
        assert c.char_count <= 600


def test_chunk_indices_are_sequential():
    text = "Some meaningful content here. " * 100
    chunks = chunk_pages([_page(1, text)], chunk_size=300, chunk_overlap=60)
    assert [c.index for c in chunks] == list(range(len(chunks)))
