"""AGENT 3 — Metadata Agent.

Responsibility: turn the planner's filters (document type/category,
department, author, date range, tags, document ids) into a concrete set of
documents to prefer, and enforce *authorization*: a user may only ever
retrieve chunks from documents they own (admins see everything).

Reuses existing metadata fields (``Document.metadata_json``) — no schema
changes. Filtering is done in Python over the user's documents for
portability across SQLite and PostgreSQL.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent, PipelineContext
from app.agents.schemas import MetadataDecision
from app.database import get_session_factory
from app.models import Document, DocumentChunk, DocumentStatus


def compute_authorized_ids(session: Session, user_id: int, is_admin: bool) -> tuple[List[int], List[int]]:
    """Return (authorized_document_ids, authorized_chunk_ids) for a user."""
    doc_query = select(Document.id).where(Document.status == DocumentStatus.completed)
    if not is_admin:
        doc_query = doc_query.where(Document.user_id == user_id)
    doc_ids = [row[0] for row in session.execute(doc_query).all()]
    if not doc_ids:
        return [], []
    chunk_ids = [
        row[0]
        for row in session.execute(select(DocumentChunk.id).where(DocumentChunk.document_id.in_(doc_ids))).all()
    ]
    return doc_ids, chunk_ids


class MetadataAgent(BaseAgent):
    name = "metadata"
    description = "Applies metadata filters (type, department, author, date, tags) and enforces access scope."
    timeout_seconds = 10.0

    async def run(self, ctx: PipelineContext) -> Tuple[str, Dict[str, Any]]:
        filters = dict(ctx.plan.filters) if ctx.plan else {}
        decision = await asyncio.to_thread(self._decide, ctx, filters)
        ctx.metadata_decision = decision

        summary = (
            f"Authorized {len(decision.authorized_document_ids)} document(s)"
            + (
                f"; filters {list(decision.applied_filters.keys())} matched {decision.matched_documents}"
                if decision.applied_filters
                else "; no metadata filters requested"
            )
        )
        return summary, {
            "authorized_documents": len(decision.authorized_document_ids),
            "applied_filters": decision.applied_filters,
            "matched_documents": decision.matched_documents,
            "total_documents": decision.total_documents,
            "fell_back_to_unfiltered": decision.fell_back_to_unfiltered,
        }

    def _decide(self, ctx: PipelineContext, filters: Dict[str, Any]) -> MetadataDecision:
        session: Session = get_session_factory()()
        try:
            # Authorization scope (always enforced)
            doc_query = select(Document).where(Document.status == DocumentStatus.completed)
            if not ctx.user.is_admin:
                doc_query = doc_query.where(Document.user_id == ctx.user.id)
            documents = list(session.execute(doc_query).scalars().all())
            authorized_ids = [d.id for d in documents]

            if not filters:
                return MetadataDecision(
                    applied_filters={},
                    matched_document_ids=None,
                    authorized_document_ids=authorized_ids,
                    total_documents=len(documents),
                    matched_documents=len(documents),
                    notes="No metadata filters requested.",
                )

            matched = [d for d in documents if _document_matches(d, filters)]
            notes = ""
            fell_back = False
            if not matched and documents:
                # Honest fallback: tell the user the filter matched nothing but
                # still surface the best semantic matches.
                notes = (
                    "No documents matched the metadata filters "
                    f"({', '.join(f'{k}={v}' for k, v in filters.items())}); "
                    "falling back to unfiltered retrieval."
                )
                fell_back = True
                matched_ids = None
            else:
                matched_ids = [d.id for d in matched]

            return MetadataDecision(
                applied_filters=filters,
                matched_document_ids=matched_ids,
                authorized_document_ids=authorized_ids,
                total_documents=len(documents),
                matched_documents=len(matched),
                notes=notes,
                fell_back_to_unfiltered=fell_back,
            )
        finally:
            session.close()


def _document_matches(document: Document, filters: Dict[str, Any]) -> bool:
    meta = document.metadata_json or {}

    category = filters.get("category")
    if category and str(meta.get("category", "")).lower() != str(category).lower():
        return False

    department = filters.get("department")
    if department and str(meta.get("department", "")).lower() != str(department).lower():
        return False

    author = filters.get("author")
    if author and author.lower() not in str(meta.get("author", "")).lower():
        return False

    tags = filters.get("tags")
    if tags:
        doc_tags = {str(t).lower() for t in (meta.get("tags") or [])}
        if not any(str(t).lower() in doc_tags for t in tags):
            return False

    year_min, year_max = filters.get("year_min"), filters.get("year_max")
    if year_min or year_max:
        doc_year = _document_year(meta)
        if doc_year is None:
            return False
        if year_min and doc_year < int(year_min):
            return False
        if year_max and doc_year > int(year_max):
            return False

    document_ids = filters.get("document_ids")
    if document_ids and document.id not in {int(i) for i in document_ids}:
        return False

    return True


def _document_year(meta: Dict[str, Any]):
    date_str = meta.get("document_date")
    if date_str and len(str(date_str)) >= 4:
        try:
            return int(str(date_str)[:4])
        except ValueError:
            return None
    for d in meta.get("dates_mentioned") or []:
        try:
            return int(str(d)[:4])
        except ValueError:
            continue
    return None
