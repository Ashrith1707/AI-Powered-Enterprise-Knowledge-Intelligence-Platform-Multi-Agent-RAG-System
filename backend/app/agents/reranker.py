"""AGENT 4 — Reranker Agent.

Responsibility: re-score retrieval candidates so the best evidence rises to
the top before compression/generation.

Pluggable strategy interface:
* ``LexicalCompositeReranker`` (default) — fast local scoring: hybrid score,
  query-term coverage, exact-phrase bonus, rare-term (IDF-like) bonus,
  multi-query agreement. No LLM cost for simple ranking.
* ``LLMReranker`` — optional pointwise LLM relevance scoring, disabled by
  default (cost), available for later cross-encoder/LLM upgrades.
"""
from __future__ import annotations

import asyncio
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Sequence, Tuple

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import RankedChunk
from app.rag.query_rewrite import extract_keywords
from app.services.embeddings import tokenize


class RerankerStrategy(ABC):
    name = "base"

    @abstractmethod
    def rerank(self, query: str, chunks: Sequence) -> List[Tuple[object, float]]:
        """Return [(chunk, score)] sorted by descending score, score in 0..1."""


class LexicalCompositeReranker(RerankerStrategy):
    """Weighted composite of ABSOLUTE relevance signals.

    Uses raw cosine similarity (vector_score) and query-term coverage rather
    than the min-max normalized RRF score, because normalized scores always
    inflate the top hit to 1.0 — which would make relevance floors useless
    and unanswerable queries impossible to refuse honestly.
    """

    name = "lexical-composite-v2"

    W_SIMILARITY = 0.40   # absolute: cosine (vector) or scaled BM25 (keyword-only)
    W_COVERAGE = 0.30     # absolute: query keyword coverage in the chunk
    W_PHRASE = 0.15       # absolute: quoted-phrase match
    W_RARE = 0.10         # absolute: rare-term (IDF-like) matches
    W_AGREEMENT = 0.05    # matched by multiple query variants

    def rerank(self, query: str, chunks: Sequence) -> List[Tuple[object, float]]:
        if not chunks:
            return []
        q_tokens = set(tokenize(query))
        q_keywords = set(extract_keywords(query, limit=12))
        phrase = _quoted_phrase(query)

        # Document-frequency of query terms across candidates (rare-term bonus).
        df: Counter = Counter()
        for chunk in chunks:
            present = set(tokenize(chunk.content))
            for term in q_tokens:
                if term in present:
                    df[term] += 1
        n = len(chunks)

        scored: List[Tuple[object, float]] = []
        for chunk in chunks:
            tokens = tokenize(chunk.content)
            token_set = set(tokens)

            coverage = (
                len(q_keywords & token_set) / len(q_keywords) if q_keywords else 0.0
            )
            phrase_bonus = 1.0 if phrase and phrase in chunk.content.lower() else 0.0
            rare = 0.0
            if q_tokens:
                idf_scores = [
                    math.log(1 + n / (1 + df.get(t, 0))) for t in q_tokens if t in token_set
                ]
                rare = min(1.0, sum(idf_scores) / (len(q_tokens) * 0.9)) if idf_scores else 0.0

            agreement = min(1.0, (len(getattr(chunk, "matched_queries", []) or []) - 1) * 0.5)

            # Absolute similarity term:
            #  * vector hit  → raw cosine (saturates at cosine 0.4)
            #  * keyword-only hit → scaled BM25 score (saturates around 6.0)
            if getattr(chunk, "vector_score", None) is not None:
                similarity = min(1.0, max(0.0, chunk.vector_score) * 2.5)
            elif getattr(chunk, "keyword_score", None) is not None:
                similarity = min(1.0, max(0.0, chunk.keyword_score) / 6.0) * 0.75
            else:
                similarity = 0.0

            score = (
                self.W_SIMILARITY * similarity
                + self.W_COVERAGE * coverage
                + self.W_PHRASE * phrase_bonus
                + self.W_RARE * rare
                + self.W_AGREEMENT * agreement
            )
            scored.append((chunk, round(min(1.0, score), 4)))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored


class LLMReranker(RerankerStrategy):
    """Optional pointwise LLM reranking (off by default — cost control)."""

    name = "llm-pointwise-v1"

    def rerank(self, query: str, chunks: Sequence) -> List[Tuple[object, float]]:
        from app.services.llm import MockLLM, get_llm_provider

        provider = get_llm_provider()
        if isinstance(provider, MockLLM):
            return LexicalCompositeReranker().rerank(query, chunks)

        scored: List[Tuple[object, float]] = []
        for chunk in chunks:
            prompt = (
                f"Question: {query}\n\nPassage: {chunk.content[:1500]}\n\n"
                "Rate how useful this passage is for answering the question. "
                "Reply with a single number from 0 to 10, nothing else."
            )
            try:
                result = provider.generate(prompt, temperature=0.0, max_output_tokens=8)
                m = re.search(r"\d+(?:\.\d+)?", result.text)
                score = (float(m.group()) / 10.0) if m else 0.0
            except Exception:  # noqa: BLE001 — reranking must not break the pipeline
                score = max(0.0, min(1.0, chunk.score))
            scored.append((chunk, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored


def _quoted_phrase(query: str) -> str:
    m = re.findall(r'"([^"]{3,80})"', query) or re.findall(r"'([^']{3,80})'", query)
    return m[0].lower() if m else ""


def get_reranker() -> RerankerStrategy:
    from app.config import get_settings

    if getattr(get_settings(), "reranker_use_llm", False):
        return LLMReranker()
    return LexicalCompositeReranker()


class RerankerAgent(BaseAgent):
    name = "reranker"
    description = "Re-scores candidate chunks with a local composite relevance model."
    timeout_seconds = 20.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, object]]:
        if not ctx.candidates:
            ctx.ranked = []
            return "No candidates to rerank.", {"ranked": 0}

        strategy = get_reranker()
        top_n = self._settings.rerank_top_n
        pairs = await asyncio.to_thread(strategy.rerank, ctx.query, ctx.candidates)

        ctx.ranked = [
            RankedChunk(**chunk.model_dump(), rerank_score=score, rerank_method=strategy.name)
            for chunk, score in pairs[:top_n]
        ]

        improved = 0
        candidate_order = {c.chunk_id: i for i, c in enumerate(ctx.candidates)}
        for new_pos, rc in enumerate(ctx.ranked):
            if candidate_order.get(rc.chunk_id, new_pos) != new_pos:
                improved += 1
        summary = (
            f"Reranked {len(ctx.candidates)} candidates with {strategy.name}; kept top {len(ctx.ranked)} "
            f"({improved} position change(s))."
        )
        return summary, {
            "method": strategy.name,
            "candidates_in": len(ctx.candidates),
            "ranked_out": len(ctx.ranked),
            "position_changes": improved,
            "top_score": ctx.ranked[0].rerank_score if ctx.ranked else 0.0,
        }
