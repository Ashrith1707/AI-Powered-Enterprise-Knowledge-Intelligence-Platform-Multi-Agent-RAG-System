"""Search routes — direct hybrid/semantic/keyword retrieval over chunks.

Authorization: results are always restricted to documents the caller owns
(admins see everything). This is the same enforcement the Retriever Agent
uses, so search can never leak another user's documents.
"""
from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.metadata import _document_matches
from app.core.deps import get_current_user_info
from app.agents.base import UserInfo
from app.database import get_db
from app.models import Document, DocumentChunk, DocumentStatus
from app.rag.bm25 import ensure_bm25_loaded
from app.rag.hybrid import fuse_rankings, normalize_scores
from app.schemas.search import SearchHit, SearchRequest, SearchResponse
from app.services.embeddings import get_embedding_provider
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/search", tags=["search"])


def _snippet(content: str, query: str, radius: int = 160) -> str:
    lowered = content.lower()
    best_pos = 0
    for term in query.lower().split():
        pos = lowered.find(term.strip())
        if pos >= 0:
            best_pos = pos
            break
    start = max(0, best_pos - radius // 2)
    end = min(len(content), start + radius * 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return prefix + content[start:end].strip() + suffix


@router.post("", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db), user: UserInfo = Depends(get_current_user_info)):
    started = time.perf_counter()

    # --- authorization scope -------------------------------------------------
    doc_query = select(Document).where(Document.status == DocumentStatus.completed)
    if not user.is_admin:
        doc_query = doc_query.where(Document.user_id == user.id)
    documents = {d.id: d for d in db.execute(doc_query).scalars().all()}

    filters = (payload.filters.model_dump(exclude_none=True) if payload.filters else {}) or {}
    filters_applied = {k: v for k, v in filters.items() if k != "document_ids"}
    if filters.get("document_ids"):
        documents = {i: d for i, d in documents.items() if i in set(filters["document_ids"])}
    if filters_applied:
        documents = {i: d for i, d in documents.items() if _document_matches(d, filters_applied)}

    if not documents:
        return SearchResponse(
            query=payload.query, mode=payload.mode, took_ms=0.0, total=0, hits=[],
            embedding_provider=get_embedding_provider().name, filters_applied=filters_applied,
        )

    allowed_chunk_ids = set(
        row[0] for row in db.execute(
            select(DocumentChunk.id).where(DocumentChunk.document_id.in_(documents.keys()))
        ).all()
    )

    # --- retrieval -------------------------------------------------------------
    vector_hits = []
    keyword_hits = []
    provider = get_embedding_provider()

    if payload.mode in ("hybrid", "semantic") and allowed_chunk_ids:
        qvec = provider.embed_query(payload.query)
        vector_hits = get_vector_store().search(qvec, payload.top_k * 2, allowed_chunk_ids=allowed_chunk_ids)
    if payload.mode in ("hybrid", "keyword") and allowed_chunk_ids:
        bm25 = ensure_bm25_loaded(db)
        keyword_hits = bm25.search(payload.query, payload.top_k * 2, allowed_chunk_ids=allowed_chunk_ids)

    fused = fuse_rankings(vector_hits, keyword_hits)
    scores = normalize_scores(fused)

    hits: List[SearchHit] = []
    chunk_ids = [h.chunk_id for h in fused[: payload.top_k]]
    if chunk_ids:
        rows = db.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        ).scalars().all()
        by_id = {r.id: r for r in rows}
        for hit, score in list(zip(fused, scores))[: payload.top_k]:
            chunk: Optional[DocumentChunk] = by_id.get(hit.chunk_id)
            if chunk is None or chunk.document_id not in documents:
                continue
            document = documents[chunk.document_id]
            meta = document.metadata_json or {}
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=str(meta.get("title") or document.filename),
                    filename=document.filename,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    score=round(score, 4),
                    sources=hit.sources,
                    snippet=_snippet(chunk.content, payload.query),
                    metadata={"category": meta.get("category"), "department": meta.get("department"),
                              "author": meta.get("author")},
                )
            )

    return SearchResponse(
        query=payload.query,
        mode=payload.mode,
        took_ms=round((time.perf_counter() - started) * 1000, 1),
        total=len(hits),
        hits=hits,
        embedding_provider=provider.name,
        filters_applied=filters_applied,
    )
