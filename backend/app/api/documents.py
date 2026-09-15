"""Document management routes (Module 2 surface, preserved contract).

Upload → validation → background ingestion with pollable progress.
Ownership is enforced on every document access (admins may access all).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.core.deps import get_current_user, write_audit
from app.core.errors import AuthorizationError, NotFoundError, UploadError
from app.core.security import generate_stored_name, sanitize_filename
from app.database import get_db
from app.models import Document, DocumentChunk, DocumentStatus, User
from app.schemas.document import (
    DocumentContentOut,
    DocumentContentPage,
    DocumentListOut,
    DocumentOut,
    DocumentStatusOut,
)
from app.services.file_validation import validate_upload
from app.services.ingestion import submit_document_processing

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_owned_document(db: Session, document_id: int, user: User) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    if document.user_id != user.id and not user.is_admin:
        # Do not leak existence of other users' documents.
        raise NotFoundError(f"Document {document_id} not found.")
    return document


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content = await file.read()
    safe_name = sanitize_filename(file.filename or "")

    try:
        validated = validate_upload(safe_name, content)
    except UploadError as exc:
        write_audit(db, user_id=user.id, action="upload", request=request, outcome="denied",
                    resource_type="document", detail={"filename": safe_name, "reason": exc.message})
        raise

    settings = get_settings()
    stored_name = generate_stored_name(safe_name)
    dest = Path(settings.upload_dir) / stored_name
    dest.write_bytes(content)  # stored under UUID name inside the upload dir

    document = Document(
        user_id=user.id,
        filename=safe_name,
        stored_filename=stored_name,
        file_type=validated.extension,
        file_size=validated.size_bytes,
        status=DocumentStatus.pending,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    write_audit(db, user_id=user.id, action="upload", request=request, resource_type="document",
                resource_id=document.id, detail={"filename": safe_name, "size": validated.size_bytes,
                                                 "type": validated.extension})

    # Background ingestion (job registry tracks fine-grained progress).
    job_id = submit_document_processing(document.id)
    _ = background_tasks  # ingestion runs on the job registry thread pool
    out = DocumentOut.from_model(document)
    out_dict = out.model_dump()
    out_dict["job_id"] = job_id
    return out


@router.get("", response_model=DocumentListOut)
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    q: str | None = None,
):
    query = select(Document)
    if not user.is_admin:
        query = query.where(Document.user_id == user.id)
    if status:
        query = query.where(Document.status == status)
    if q:
        query = query.where(Document.filename.ilike(f"%{q.strip()}%"))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    rows = db.execute(
        query.options(joinedload(Document.owner))
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().scalars().all()

    chunk_counts = dict(
        db.execute(
            select(DocumentChunk.document_id, func.count(DocumentChunk.id))
            .group_by(DocumentChunk.document_id)
        ).all()
    )
    items = []
    for doc in rows:
        out = DocumentOut.from_model(doc)
        out.chunk_count = chunk_counts.get(doc.id, 0)
        items.append(out)
    return DocumentListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = _get_owned_document(db, document_id, user)
    out = DocumentOut.from_model(document)
    out.chunk_count = db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document.id)
    ).scalar() or 0
    return out


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def get_document_status(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = _get_owned_document(db, document_id, user)
    job_info = None
    from app.services.jobs import get_job_registry

    # Find the most recent job for this document (registry keys start with doc-<id>-)
    registry = get_job_registry()
    for job_id in list(registry._jobs.keys())[::-1]:  # newest first (insertion order)
        if job_id.startswith(f"doc-{document.id}-"):
            job_info = registry.get(job_id).as_dict()
            break
    return DocumentStatusOut(
        document_id=document.id,
        status=document.status.value,
        stage=document.processing_stage,
        progress=document.processing_progress or 0,
        error_message=document.error_message,
        job=job_info,
    )


@router.get("/{document_id}/content", response_model=DocumentContentOut)
def get_document_content(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    max_pages: int = Query(50, ge=1, le=500),
):
    """Preview extracted text grouped by page (from chunks — no re-parsing)."""
    document = _get_owned_document(db, document_id, user)
    chunks = db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
    ).scalars().all()

    pages: dict[int, list[str]] = {}
    for chunk in chunks:
        pages.setdefault(chunk.page_start, []).append(chunk.content)
    page_out = [
        DocumentContentPage(page=p, text="\n\n".join(texts)[:20000])
        for p, texts in sorted(pages.items())[:max_pages]
    ]
    return DocumentContentOut(document_id=document.id, filename=document.filename, pages=page_out)


@router.post("/{document_id}/reprocess", response_model=DocumentStatusOut, status_code=202)
def reprocess_document(
    document_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    document = _get_owned_document(db, document_id, user)
    settings = get_settings()
    path = Path(settings.upload_dir) / document.stored_filename
    if not path.exists():
        raise NotFoundError("Stored file is missing; please upload the document again.")
    document.status = DocumentStatus.pending
    document.processing_stage = "queued"
    document.processing_progress = 0
    document.error_message = None
    db.commit()
    submit_document_processing(document.id)
    write_audit(db, user_id=user.id, action="reprocess", request=request,
                resource_type="document", resource_id=document.id)
    return DocumentStatusOut(document_id=document.id, status="pending", stage="queued", progress=0)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    document = _get_owned_document(db, document_id, user)

    # Remove vectors + BM25 entries + the stored file, then cascade-delete rows.
    chunk_ids = [
        row[0] for row in db.execute(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
        ).all()
    ]
    if chunk_ids:
        from app.rag.bm25 import get_bm25_index
        from app.services.vector_store import get_vector_store

        get_vector_store().remove(chunk_ids)
        get_bm25_index().remove(chunk_ids)

    path = Path(get_settings().upload_dir) / document.stored_filename
    if path.exists():
        path.unlink(missing_ok=True)

    write_audit(db, user_id=user.id, action="delete_document", request=request,
                resource_type="document", resource_id=document.id,
                detail={"filename": document.filename, "chunks_removed": len(chunk_ids)})
    db.delete(document)
    db.commit()
    return None
