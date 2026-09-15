"""Page-aware recursive chunking.

Chunks keep a mapping to source pages (page_start / page_end) so every
citation can point at document + page. Splitting is recursive:
paragraphs → sentences → words, with configurable size/overlap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

from app.services.parsing import PageText


@dataclass
class TextChunk:
    index: int
    content: str
    page_start: int
    page_end: int
    char_count: int


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WS_RE = re.compile(r"\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _hard_split(text: str, size: int) -> List[str]:
    """Word-level split for sentences longer than the chunk size."""
    words = text.split(" ")
    out: List[str] = []
    current: List[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > size and current:
            out.append(" ".join(current))
            # keep a small tail for continuity
            current = current[-max(1, size // 20):]
            length = sum(len(w) + 1 for w in current)
        current.append(word)
        length += len(word) + 1
    if current:
        out.append(" ".join(current))
    return out


def chunk_pages(
    pages: Sequence[PageText],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[TextChunk]:
    """Chunk page-aware text into overlapping pieces.

    The overlap is applied at sentence granularity: the tail sentences of the
    previous chunk are prepended to the next one, preserving page attribution.
    """
    if chunk_overlap >= chunk_size:
        chunk_overlap = chunk_size // 5

    chunks: List[TextChunk] = []
    buffer: List[tuple[str, int]] = []  # (sentence, page_number)
    buffer_len = 0

    def flush(keep_tail: bool) -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        content = _WS_RE.sub(" ", " ".join(s for s, _ in buffer)).strip()
        if content:
            page_start = buffer[0][1]
            page_end = buffer[-1][1]
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    content=content,
                    page_start=page_start,
                    page_end=page_end,
                    char_count=len(content),
                )
            )
        if keep_tail and chunk_overlap > 0:
            tail: List[tuple[str, int]] = []
            tail_len = 0
            for sent, page in reversed(buffer):
                if tail_len + len(sent) > chunk_overlap:
                    break
                tail.insert(0, (sent, page))
                tail_len += len(sent)
            buffer, buffer_len = tail, tail_len
        else:
            buffer, buffer_len = [], 0

    for page in pages:
        for sentence in _sentences(page.text):
            if len(sentence) > chunk_size:
                # Oversized sentence: flush current buffer, then hard-split.
                flush(keep_tail=False)
                for piece in _hard_split(sentence, chunk_size):
                    chunks.append(
                        TextChunk(
                            index=len(chunks),
                            content=piece,
                            page_start=page.number,
                            page_end=page.number,
                            char_count=len(piece),
                        )
                    )
                continue
            buffer.append((sentence, page.number))
            buffer_len += len(sentence) + 1
            if buffer_len >= chunk_size:
                flush(keep_tail=True)
    flush(keep_tail=False)

    # Drop trivially small trailing chunks (< 40 chars) unless it's all we have.
    if len(chunks) > 1 and chunks[-1].char_count < 40:
        chunks.pop()
    for i, c in enumerate(chunks):
        c.index = i
    return chunks
