"""AGENT 5 — Context Compression Agent.

Responsibility: turn ranked chunks into a compact evidence context:
* remove near-duplicate chunks (shingled Jaccard);
* drop chunks below the relevance floor;
* extract query-relevant sentences from long chunks;
* enforce the evidence character budget, highest-scoring evidence first;
* NEVER drop citation metadata (chunk id, document, pages) — every evidence
  block keeps full provenance and gets a stable id (E1, E2, ...).
"""
from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Sequence, Set, Tuple

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import CompressedContext, Evidence
from app.rag.query_rewrite import extract_keywords
from app.services.embeddings import tokenize

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_MAX_SENTENCES_PER_EVIDENCE = 6
_MAX_EVIDENCE_CHARS = 700


def _shingles(tokens: Sequence[str], k: int = 5) -> Set[str]:
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_near_duplicate(a: str, b: str, threshold: float) -> bool:
    return jaccard(_shingles(tokenize(a)), _shingles(tokenize(b))) >= threshold


def select_relevant_sentences(content: str, keywords: List[str], max_chars: int = _MAX_EVIDENCE_CHARS) -> str:
    """Keep only query-relevant sentences, preserving document order and the length cap.

    A sentence is kept when it shares at least one query keyword; ranking (with
    a small first-sentence context bonus) decides which of them survive the
    character budget. If nothing matches, the leading sentences are kept so the
    evidence still gives document context.
    """
    sentences = [s.strip() for s in _SENT_RE.split(content) if s.strip()]
    if len(sentences) <= 1 or len(content) <= max_chars:
        return content[:max_chars]

    kw = set(keywords)
    scored: List[Tuple[int, float, float, str]] = []  # (pos, overlap, rank_score, sentence)
    for i, s in enumerate(sentences):
        toks = set(tokenize(s))
        overlap = len(kw & toks) / max(1, len(kw))
        position_bonus = 0.1 if i == 0 else 0.0  # first sentence carries context
        scored.append((i, overlap, overlap + position_bonus, s))

    relevant = [t for t in scored if t[1] > 0]
    if not relevant:
        relevant = scored[:2]  # keep leading context when no keyword overlap

    relevant.sort(key=lambda t: t[2], reverse=True)
    selected: List[Tuple[int, str]] = []
    used = 0
    for pos, _overlap, _rank, sentence in relevant:
        if used + len(sentence) > max_chars and selected:
            continue  # try a shorter, still-relevant sentence
        selected.append((pos, sentence))
        used += len(sentence) + 1
        if len(selected) >= _MAX_SENTENCES_PER_EVIDENCE:
            break

    selected.sort(key=lambda t: t[0])  # restore document order
    text = " ".join(s for _, s in selected)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


class ContextCompressionAgent(BaseAgent):
    name = "compressor"
    description = "Deduplicates and compresses ranked evidence within a token budget, keeping citations intact."
    timeout_seconds = 15.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, object]]:
        if not ctx.ranked:
            ctx.compressed = CompressedContext(evidences=[], budget_chars=self._settings.max_evidence_chars)
            return "No ranked chunks to compress.", {"evidences": 0}

        compressed = await asyncio.to_thread(self._compress, ctx)
        ctx.compressed = compressed

        if not compressed.evidences and ctx.ranked:
            summary = (
                f"All {len(ctx.ranked)} ranked chunk(s) fell below the absolute relevance floor "
                f"({self._settings.min_relevance_score}) — the knowledge base has no usable evidence "
                "for this question; the generator will refuse honestly."
            )
            return summary, {
                "evidences": 0, "removed_low_relevance": compressed.removed_low_relevance,
                "removed_duplicates": compressed.removed_duplicates,
                "relevance_floor": self._settings.min_relevance_score,
            }

        ratio = (
            round(1 - compressed.total_chars / compressed.chars_before, 2)
            if compressed.chars_before else 0.0
        )
        summary = (
            f"Compressed {len(ctx.ranked)} ranked chunk(s) into {len(compressed.evidences)} evidence block(s): "
            f"{compressed.chars_before} → {compressed.total_chars} chars "
            f"({int(ratio * 100)}% reduction; {compressed.removed_duplicates} duplicate(s), "
            f"{compressed.removed_low_relevance} low-relevance dropped)."
        )
        return summary, {
            "evidences": len(compressed.evidences),
            "chars_before": compressed.chars_before,
            "chars_after": compressed.total_chars,
            "reduction_ratio": ratio,
            "removed_duplicates": compressed.removed_duplicates,
            "removed_low_relevance": compressed.removed_low_relevance,
        }

    def _compress(self, ctx: PipelineContext) -> CompressedContext:
        settings = self._settings
        budget = settings.max_evidence_chars
        keywords = extract_keywords(ctx.query, limit=10)

        kept: List[Evidence] = []
        kept_texts: List[str] = []
        removed_duplicates = 0
        removed_low = 0
        chars_before = sum(len(c.content) for c in ctx.ranked)
        used = 0

        # When the Metadata Agent actively narrowed the scope (filters matched
        # documents), trust that scoping and always keep the top-2 candidates.
        decision = ctx.metadata_decision
        trust_metadata_scope = bool(
            decision is not None
            and decision.applied_filters
            and decision.matched_document_ids
            and not decision.fell_back_to_unfiltered
        )

        for rank, chunk in enumerate(ctx.ranked, start=1):
            # Relevance floor applied to ALL ranks (absolute scores from the
            # reranker) — this is what enables honest refusal for questions
            # the knowledge base cannot answer.
            if chunk.rerank_score < settings.min_relevance_score:
                if trust_metadata_scope and rank <= 2:
                    pass  # keep: user-scoped retrieval via explicit filters
                else:
                    removed_low += 1
                    continue
            # 2. duplicate removal against already-kept evidence
            if any(is_near_duplicate(chunk.content, t, settings.dedup_jaccard_threshold) for t in kept_texts):
                removed_duplicates += 1
                continue

            text = select_relevant_sentences(chunk.content, keywords)
            if used + len(text) > budget and kept:
                # Budget exhausted — stop; remaining evidence is lower-scoring.
                break

            evidence = Evidence(
                evidence_id=f"E{len(kept) + 1}",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                filename=chunk.filename,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=text,
                score=chunk.rerank_score,
                original_chars=len(chunk.content),
                compressed_chars=len(text),
            )
            kept.append(evidence)
            kept_texts.append(chunk.content)
            used += len(text)

        return CompressedContext(
            evidences=kept,
            total_chars=used,
            budget_chars=budget,
            removed_duplicates=removed_duplicates,
            removed_low_relevance=removed_low,
            chars_before=chars_before,
        )
