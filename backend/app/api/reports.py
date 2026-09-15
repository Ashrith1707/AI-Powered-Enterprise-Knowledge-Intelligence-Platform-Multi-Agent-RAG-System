"""Report routes — generated summaries + CSV export of real system data."""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Conversation, Document, DocumentChunk, Message, User
from app.services.embeddings import embedding_provider_status
from app.services.llm import get_llm_provider
from app.services.vector_store import vector_store_status

router = APIRouter(prefix="/reports", tags=["reports"])


def _scope(user: User):
    return {} if user.is_admin else {"user_id": user.id}


@router.get("/summary")
def report_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scope = _scope(user)
    documents = db.execute(select(Document).filter_by(**scope).order_by(Document.created_at.desc())).scalars().all()

    status_counts = Counter(d.status.value for d in documents)
    type_counts = Counter(d.file_type for d in documents)
    department_counts = Counter(
        (d.metadata_json or {}).get("department") or "unclassified" for d in documents
    )
    category_counts = Counter(
        (d.metadata_json or {}).get("category") or "unclassified" for d in documents
    )

    doc_ids = [d.id for d in documents]
    chunk_count = 0
    if doc_ids:
        chunk_count = db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id.in_(doc_ids))
        ).scalar() or 0

    conv_ids = [row[0] for row in db.execute(select(Conversation.id).filter_by(**scope)).all()]
    questions = 0
    verified_answers = 0
    total_answers = 0
    cited_documents: Counter = Counter()
    if conv_ids:
        questions = db.execute(
            select(func.count(Message.id)).where(Message.conversation_id.in_(conv_ids), Message.role == "user")
        ).scalar() or 0
        assistant_rows = db.execute(
            select(Message).where(Message.conversation_id.in_(conv_ids), Message.role == "assistant")
        ).scalars().all()
        total_answers = len(assistant_rows)
        for m in assistant_rows:
            metrics = m.metrics_json or {}
            if metrics.get("verification_failures", 0) == 0:
                verified_answers += 1
            for c in m.citations_json or []:
                cited_documents[c.get("document_id")] += 1

    top_cited = []
    for doc_id, count in cited_documents.most_common(5):
        document = db.get(Document, doc_id)
        if document:
            top_cited.append({"document_id": doc_id, "filename": document.filename, "citations": count})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": {
            "llm_provider": get_llm_provider().name,
            "embeddings": embedding_provider_status(),
            "vector_store": vector_store_status(),
        },
        "documents": {
            "total": len(documents),
            "by_status": dict(status_counts),
            "by_type": dict(type_counts),
            "by_department": dict(department_counts),
            "by_category": dict(category_counts),
            "total_chunks": chunk_count,
            "total_chars": sum(d.char_count or 0 for d in documents),
        },
        "usage": {
            "conversations": len(conv_ids),
            "questions_asked": questions,
            "answers_generated": total_answers,
            "answers_passing_verification": verified_answers,
            "verification_rate": round(verified_answers / total_answers, 3) if total_answers else None,
        },
        "top_cited_documents": top_cited,
        "recent_documents": [
            {
                "id": d.id, "filename": d.filename, "status": d.status.value,
                "pages": d.page_count, "chunks": len(d.chunks) if d.chunks else 0,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents[:10]
        ],
    }


@router.get("/export")
def export_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """CSV export of the document inventory (real rows only)."""
    scope = _scope(user)
    documents = db.execute(select(Document).filter_by(**scope).order_by(Document.id)).scalars().all()
    doc_ids = [d.id for d in documents]
    chunk_counts = dict(
        db.execute(
            select(DocumentChunk.document_id, func.count(DocumentChunk.id))
            .where(DocumentChunk.document_id.in_(doc_ids))
            .group_by(DocumentChunk.document_id)
        ).all()
    ) if doc_ids else {}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "filename", "type", "status", "size_bytes", "pages", "chunks", "chars",
        "title", "author", "department", "category", "document_date", "ocr_used",
        "created_at", "completed_at",
    ])
    for d in documents:
        meta = d.metadata_json or {}
        writer.writerow([
            d.id, d.filename, d.file_type, d.status.value, d.file_size, d.page_count,
            chunk_counts.get(d.id, 0), d.char_count,
            meta.get("title", ""), meta.get("author", ""), meta.get("department", ""),
            meta.get("category", ""), meta.get("document_date", ""), bool(d.ocr_used),
            d.created_at.isoformat() if d.created_at else "",
            d.processing_completed_at.isoformat() if d.processing_completed_at else "",
        ])
    buffer.seek(0)
    filename = f"knowledgeiq-documents-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
