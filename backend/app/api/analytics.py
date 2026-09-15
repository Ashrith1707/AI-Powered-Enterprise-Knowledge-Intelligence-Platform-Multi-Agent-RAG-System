"""Analytics routes — dashboard/aggregations computed from real data.

All numbers come from actual DB rows and persisted agent traces/metrics —
nothing is fabricated.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Conversation, Document, DocumentChunk, DocumentStatus, Message, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _scope(user: User):
    return {} if user.is_admin else {"user_id": user.id}


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = _scope(user)

    status_rows = db.execute(
        select(Document.status, func.count(Document.id)).filter_by(**scope).group_by(Document.status)
    ).all()
    status_counts = {(s.value if hasattr(s, "value") else str(s)): c for s, c in status_rows}

    doc_ids = [row[0] for row in db.execute(select(Document.id).filter_by(**scope)).all()]
    total_chunks = 0
    if doc_ids:
        total_chunks = db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id.in_(doc_ids))
        ).scalar() or 0

    conv_ids = [row[0] for row in db.execute(select(Conversation.id).filter_by(**scope)).all()]
    questions = 0
    answers = 0
    if conv_ids:
        questions = db.execute(
            select(func.count(Message.id)).where(Message.conversation_id.in_(conv_ids), Message.role == "user")
        ).scalar() or 0
        answers = db.execute(
            select(func.count(Message.id)).where(Message.conversation_id.in_(conv_ids), Message.role == "assistant")
        ).scalar() or 0

    # Uploads over the last 14 days
    since = datetime.now(timezone.utc) - timedelta(days=13)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_docs = db.execute(
        select(Document.created_at).filter_by(**scope).where(Document.created_at >= since)
    ).scalars().all()
    per_day = Counter(d.date().isoformat() for d in recent_docs if d)
    days = [(since + timedelta(days=i)).date().isoformat() for i in range(14)]
    uploads_series = [{"date": day, "count": per_day.get(day, 0)} for day in days]

    total_bytes = db.execute(select(func.coalesce(func.sum(Document.file_size), 0)).filter_by(**scope)).scalar() or 0
    total_chars = db.execute(select(func.coalesce(func.sum(Document.char_count), 0)).filter_by(**scope)).scalar() or 0

    return {
        "documents_total": sum(status_counts.values()),
        "documents_by_status": status_counts,
        "total_chunks": total_chunks,
        "total_bytes": int(total_bytes),
        "total_chars": int(total_chars),
        "conversations": len(conv_ids),
        "questions_asked": questions,
        "answers_generated": answers,
        "uploads_last_14_days": uploads_series,
    }


@router.get("/performance")
def performance(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Latency/verification stats aggregated from persisted assistant-message metrics."""
    conv_ids = select(Conversation.id).where(Conversation.user_id == user.id) if not user.is_admin \
        else select(Conversation.id)
    rows = db.execute(
        select(Message.metrics_json).where(
            Message.conversation_id.in_(conv_ids), Message.role == "assistant"
        ).order_by(Message.id.desc()).limit(200)
    ).scalars().all()

    metrics = [m for m in rows if m]
    def _avg(key: str) -> float | None:
        values = [m.get(key) for m in metrics if isinstance(m.get(key), (int, float))]
        return round(sum(values) / len(values), 1) if values else None

    def _p95(key: str) -> float | None:
        values = sorted(m.get(key) for m in metrics if isinstance(m.get(key), (int, float)))
        if not values:
            return None
        idx = max(0, int(len(values) * 0.95) - 1)
        return round(values[idx], 1)

    verified = sum(1 for m in metrics if (m.get("verification_failures") or 0) == 0)
    regenerations = sum(int(m.get("regenerations") or 0) for m in metrics)
    providers = Counter(m.get("llm_provider") for m in metrics if m.get("llm_provider"))

    return {
        "sample_size": len(metrics),
        "avg_total_latency_ms": _avg("total_latency_ms"),
        "p95_total_latency_ms": _p95("total_latency_ms"),
        "avg_retrieval_latency_ms": _avg("retrieval_latency_ms"),
        "avg_generation_latency_ms": _avg("generation_latency_ms"),
        "avg_verification_latency_ms": _avg("verification_latency_ms"),
        "avg_chunks_retrieved": _avg("chunks_retrieved"),
        "answers_without_verification_failure": verified,
        "total_regenerations": regenerations,
        "provider_usage": dict(providers),
    }


@router.get("/top-documents")
def top_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Documents cited most often in answers (from persisted citations)."""
    conv_ids = select(Conversation.id).where(Conversation.user_id == user.id) if not user.is_admin \
        else select(Conversation.id)
    rows = db.execute(
        select(Message.citations_json).where(
            Message.conversation_id.in_(conv_ids), Message.role == "assistant"
        ).order_by(Message.id.desc()).limit(300)
    ).scalars().all()

    counts: Counter = Counter()
    for citations in rows:
        for citation in citations or []:
            doc_id = citation.get("document_id")
            if doc_id is not None:
                counts[int(doc_id)] += 1

    out = []
    for doc_id, count in counts.most_common(8):
        document = db.get(Document, doc_id)
        if document is None:
            continue
        if not user.is_admin and document.user_id != user.id:
            continue
        meta = document.metadata_json or {}
        out.append({
            "document_id": doc_id,
            "filename": document.filename,
            "title": meta.get("title") or document.filename,
            "citations": count,
            "status": document.status.value,
        })
    return {"items": out}
