"""Lightweight lexical reranker layered on top of dense retrieval.

Blends the FAISS cosine score with query-term overlap. Catches cases where
dense similarity is high but the chunk doesn't actually contain the
query's key terms — a cheap stand-in for a cross-encoder.
"""
import re

from app.core.config import settings
from app.rag.retriever import RetrievedChunk


class Reranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk],
               top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or settings.reranker_top_k
        query_terms = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        if not query_terms:
            return chunks[:top_k]

        def blended(chunk: RetrievedChunk) -> float:
            chunk_terms = set(re.findall(r"[a-z0-9]{3,}", chunk.text.lower()))
            overlap = len(query_terms & chunk_terms) / len(query_terms)
            return 0.7 * chunk.score + 0.3 * overlap

        ranked = sorted(chunks, key=blended, reverse=True)[:top_k]
        for chunk in ranked:
            chunk.score = round(blended(chunk), 4)
        return ranked
