"""Splits page texts into overlapping retrieval chunks.

Page-aware on purpose: every chunk keeps its page number so citations
can point the user to the exact page of the source document.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings


class Chunker:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_pages(self, pages: list[dict]) -> list[dict]:
        """pages: [{page_number, text}] -> [{page_number, chunk_index, text, token_estimate}]"""
        chunks = []
        index = 0
        for page in pages:
            if not page["text"].strip():
                continue
            for piece in self.splitter.split_text(page["text"]):
                chunks.append({
                    "page_number": page["page_number"],
                    "chunk_index": index,
                    "text": piece,
                    "token_estimate": max(1, len(piece) // 4),
                })
                index += 1
        return chunks
