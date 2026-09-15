"""AGENT 2 — Retriever Agent.

Responsibility: retrieve relevant enterprise knowledge.

* multi-query retrieval: embeds every planner sub-query variant;
* vector retrieval: FAISS cosine search restricted to the user's authorized
  chunks (authorization is enforced here — never after generation);
* keyword retrieval: in-memory BM25;
* hybrid fusion: Reciprocal Rank Fusion per query, merged across queries with
  duplicate-chunk elimination (highest fused score wins, all matches kept in
  ``matched_queries``);
* retrieval scoring: normalized 0..1 scores for the reranker.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import RetrievedChunk
from app.core.logging_conf import get_logger
from app.database import get_session_factory
from app.models import Document, DocumentChunk
from app.rag.bm25 import ensure_bm25_loaded
from app.rag.hybrid import fuse_rankings, normalize_scores

logger = get_logger("retriever")


class RetrieverAgent(BaseAgent):
    name = "retriever"
    description = "Hybrid (vector + BM25) multi-query retrieval over authorized chunks."
    timeout_seconds = 30.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, object]]:
        plan = ctx.plan
        queries: List[str] = (plan.sub_queries if plan and plan.sub_queries else [ctx.query])[:3]
        top_k = plan.top_k if plan else self._settings.retrieval_top_k

        if not ctx.authorized_chunk_ids:
            ctx.candidates = []
            return "No authorized/indexed documents available to search.", {"candidates": 0}

        candidates = await asyncio.to_thread(self._retrieve, ctx, queries, top_k)
        ctx.candidates = candidates

        vector_only = sum(1 for c in candidates if c.sources == ["vector"])
        keyword_only = sum(1 for c in candidates if c.sources == ["keyword"])
        both = sum(1 for c in candidates if len(c.sources) > 1)
        summary = (
            f"Retrieved {len(candidates)} candidate chunk(s) for {len(queries)} query variant(s): "
            f"{both} hybrid, {vector_only} vector-only, {keyword_only} keyword-only."
        )
        return summary, {
            "candidates": len(candidates),
            "queries": len(queries),
            "top_k": top_k,
            "hybrid_matches": both,
            "vector_only_matches": vector_only,
            "keyword_only_matches": keyword_only,
            "strategy": plan.strategy if plan else "hybrid",
        }

    # ------------------------------------------------------------------
    def _retrieve(self, ctx: PipelineContext, queries: List[str], top_k: int) -> List[RetrievedChunk]:
        from app.services.embeddings import get_embedding_provider
        from app.services.vector_store import get_vector_store

        settings = self._settings
        allowed = set(ctx.authorized_chunk_ids or [])

        # Embed all query variants in one batch call.
        provider = get_embedding_provider()
        query_vectors = provider.embed_texts(queries)
        store = get_vector_store()

        session: Session = get_session_factory()()
        try:
            bm25 = ensure_bm25_loaded(session)

            merged: Dict[int, RetrievedChunk] = {}
            for q_idx, (query, qvec) in enumerate(zip(queries, query_vectors)):
                strategy = (ctx.plan.strategy if ctx.plan else "hybrid") or "hybrid"
                vector_hits: List[Tuple[int, float]] = []
                keyword_hits: List[Tuple[int, float]] = []

                if strategy in ("hybrid", "vector"):
                    vector_hits = store.search(qvec, top_k, allowed_chunk_ids=allowed)
                if strategy in ("hybrid", "keyword"):
                    keyword_hits = bm25.search(query, top_k, allowed_chunk_ids=allowed)

                fused = fuse_rankings(vector_hits, keyword_hits, rrf_k=settings.hybrid_rrf_k)
                norm = normalize_scores(fused)

                for hit, score in zip(fused, norm):
                    existing = merged.get(hit.chunk_id)
                    if existing:
                        # Duplicate elimination across query variants.
                        existing.score = max(existing.score, score)
                        if hit.vector_rank and (existing.vector_rank is None or hit.vector_rank < existing.vector_rank):
                            existing.vector_rank, existing.vector_score = hit.vector_rank, hit.vector_score
                        if hit.keyword_rank and (existing.keyword_rank is None or hit.keyword_rank < existing.keyword_rank):
                            existing.keyword_rank, existing.keyword_score = hit.keyword_rank, hit.keyword_score
                        for src in hit.sources:
                            if src not in existing.sources:
                                existing.sources.append(src)
                        if query not in existing.matched_queries:
                            existing.matched_queries.append(query)
                    else:
                        merged[hit.chunk_id] = RetrievedChunk(
                            chunk_id=hit.chunk_id,
                            document_id=-1,  # filled below
                            content="",
                            score=score,
                            sources=list(hit.sources),
                            vector_rank=hit.vector_rank,
                            vector_score=hit.vector_score,
                            keyword_rank=hit.keyword_rank,
                            keyword_score=hit.keyword_score,
                            matched_queries=[query],
                        )

            if not merged:
                return []

            # Hydrate chunk + document data in one query pair.
            chunk_ids = list(merged.keys())
            rows = session.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.id.in_(chunk_ids))
            ).all()

            candidates: List[RetrievedChunk] = []
            for chunk, document in rows:
                item = merged.get(chunk.id)
                if item is None:
                    continue
                meta = document.metadata_json or {}
                item.document_id = document.id
                item.document_title = str(meta.get("title") or document.filename)
                item.filename = document.filename
                item.page_start = chunk.page_start
                item.page_end = chunk.page_end
                item.content = chunk.content
                candidates.append(item)

            # Drop any chunk whose DB row vanished (deleted mid-flight)
            candidates.sort(key=lambda c: c.score, reverse=True)
            return candidates[: max(top_k * 2, top_k + 4)]
        finally:
            session.close()
