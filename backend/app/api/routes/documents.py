"""Document APIs: upload, list, detail, pages, download, patch, delete, reprocess."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.activity_repository import ActivityRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (DocumentDetailOut, DocumentOut, DocumentPatch,
                                  PageOut, UploadResponse)
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api/documents", tags=["documents"])
storage = StorageService()


def _run_pipeline(document_id: int) -> None:
    """Background task — needs its own DB session (request session is closed)."""
    from app.services.pipeline_service import PipelineService
    db = SessionLocal()
    try:
        PipelineService(db).process(document_id)
    finally:
        db.close()


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(background: BackgroundTasks,
                          file: UploadFile = File(...),
                          db: Session = Depends(get_db)):
    content = await file.read()
    file_type = storage.validate(file.filename, content)
    checksum = storage.checksum(content)

    repo = DocumentRepository(db)
    if repo.get_by_checksum(checksum):
        raise ValidationError("This exact file has already been uploaded.")

    path = storage.save(file.filename, content)
    doc = repo.create(filename=file.filename, stored_path=str(path),
                      file_type=file_type, file_size=len(content), checksum=checksum)
    ActivityRepository(db).audit("api", "document.uploaded", "document", doc.id,
                                 {"filename": file.filename, "size": len(content)})
    background.add_task(_run_pipeline, doc.id)
    return UploadResponse(document=DocumentOut.model_validate(doc),
                          message="Uploaded. Processing started in background.")


@router.get("", response_model=list[DocumentOut])
def list_documents(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return DocumentRepository(db).list_all(limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = DocumentRepository(db).get(document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return doc


@router.get("/{document_id}/pages", response_model=list[PageOut])
def get_pages(document_id: int, db: Session = Depends(get_db)):
    repo = DocumentRepository(db)
    if repo.get(document_id) is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return repo.get_pages(document_id)


@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    """Streams the ORIGINAL uploaded file with its real name and MIME type."""
    doc = DocumentRepository(db).get(document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.")
    path = Path(doc.stored_path)
    if not path.exists():
        raise NotFoundError("Stored file is missing on disk.")
    media_type = mimetypes.guess_type(doc.filename)[0] or "application/octet-stream"
    # FileResponse streams in chunks (large-file safe) and sets Content-Disposition.
    return FileResponse(path, media_type=media_type, filename=doc.filename)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(document_id: int, body: DocumentPatch, db: Session = Depends(get_db)):
    repo = DocumentRepository(db)
    doc = repo.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise ValidationError("Nothing to update.")
    for field, value in changes.items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)
    ActivityRepository(db).audit("api", "document.updated", "document", doc.id,
                                 {"fields": list(changes.keys())})
    return doc


@router.post("/{document_id}/reprocess", response_model=DocumentOut, status_code=202)
def reprocess_document(document_id: int, background: BackgroundTasks,
                       db: Session = Depends(get_db)):
    """Retry hook for failed pipeline runs (background job restart)."""
    repo = DocumentRepository(db)
    doc = repo.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.")
    # Remove old vectors + chunks so re-indexing starts clean.
    chunk_ids = [c.id for c in doc.chunks]
    if chunk_ids:
        from app.rag.vector_store import get_vector_store
        get_vector_store().remove(chunk_ids)
    ChunkRepository(db).delete_for_document(document_id)
    from app.rag.bm25 import lexical_index
    lexical_index.mark_dirty()
    repo.set_status(doc, "uploaded")
    background.add_task(_run_pipeline, doc.id)
    return doc


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    repo = DocumentRepository(db)
    doc = repo.get(document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.")

    # Remove vectors first, then rows, then the file on disk.
    chunk_ids = [c.id for c in doc.chunks]
    if chunk_ids:
        from app.rag.vector_store import get_vector_store
        get_vector_store().remove(chunk_ids)
    ChunkRepository(db).delete_for_document(document_id)
    from app.rag.bm25 import lexical_index
    lexical_index.mark_dirty()
    storage.delete(doc.stored_path)
    ActivityRepository(db).audit("api", "document.deleted", "document", document_id)
    repo.delete(doc)
