"""Document ingestion pipeline (Module 2 core + Module 5 embedding path).

Upload → Validation → Parse → (OCR if scanned) → Metadata → Entities →
Chunk → Embed → FAISS + DB chunks → BM25 index.

The pipeline is a plain function so it can run either:
  * synchronously (tests, evaluation), or
  * as a background job (API uploads) via :mod:`app.services.jobs`.

Every stage updates Document.status / processing_stage / processing_progress
so the frontend can poll real progress.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.errors import DocumentProcessingError
from app.core.logging_conf import get_logger
from app.database import session_scope
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.chunking import chunk_pages
from app.services.entity_extraction import extract_entities
from app.services.embeddings import get_embedding_provider
from app.services.metadata_extraction import extract_metadata
from app.services.ocr import ocr_image_file, ocr_scanned_pdf
from app.services.parsing import parse_file
from app.services.vector_store import get_vector_store

logger = get_logger("ingestion")

ProgressFn = Callable[[str, int], None]


def _noop_progress(stage: str, percent: int) -> None:  # pragma: no cover
    pass


def process_document_sync(document_id: int, progress: ProgressFn = _noop_progress) -> dict:
    """Run the full ingestion pipeline for one document (blocking)."""
    from app.config import get_settings
    from app.rag.bm25 import get_bm25_index

    settings = get_settings()
    started = time.perf_counter()

    with session_scope() as session:
        document: Optional[Document] = session.get(Document, document_id)
        if document is None:
            raise DocumentProcessingError(f"Document {document_id} not found.")

        document.status = DocumentStatus.processing
        document.processing_started_at = datetime.now(timezone.utc)
        document.error_message = None
        session.commit()

        try:
            # --- 1. Locate & parse -------------------------------------------
            progress("parsing", 10)
            document.processing_stage = "parsing"
            document.processing_progress = 10
            session.commit()

            file_path = Path(settings.upload_dir) / document.stored_filename
            if not file_path.exists():
                raise DocumentProcessingError("Stored file is missing from the upload directory.")

            parsed = parse_file(file_path, document.file_type)

            # --- 2. OCR when required ----------------------------------------
            if parsed.needs_ocr:
                progress("ocr", 25)
                document.status = DocumentStatus.ocr
                document.processing_stage = "ocr"
                document.processing_progress = 25
                session.commit()

                if document.file_type == "pdf":
                    page_texts = ocr_scanned_pdf(file_path)
                    from app.services.parsing import PageText

                    parsed.pages = [PageText(i + 1, t) for i, t in enumerate(page_texts)]
                else:
                    text = ocr_image_file(file_path)
                    from app.services.parsing import PageText

                    parsed.pages = [PageText(1, text)]
                parsed.ocr_attempted = True
                parsed.needs_ocr = False

            if not parsed.full_text.strip():
                raise DocumentProcessingError(
                    "No text could be extracted from this document. If it is a scanned file, "
                    "OCR support (tesseract) must be installed on the server."
                )

            # --- 3. Metadata & entities ---------------------------------------
            progress("metadata", 45)
            document.processing_stage = "metadata"
            document.processing_progress = 45
            session.commit()

            document.metadata_json = extract_metadata(parsed, fallback_title=document.filename)
            document.entities_json = extract_entities(parsed.full_text)
            document.page_count = parsed.page_count
            document.char_count = parsed.char_count
            document.ocr_used = 1 if parsed.ocr_attempted else 0

            # --- 4. Chunking ---------------------------------------------------
            progress("chunking", 55)
            document.processing_stage = "chunking"
            document.processing_progress = 55
            session.commit()

            chunks = chunk_pages(parsed.pages, settings.chunk_size, settings.chunk_overlap)
            if not chunks:
                raise DocumentProcessingError("Chunking produced no chunks.")

            # Replace any previous chunks (reprocessing case)
            if document.chunks:
                old_ids = [c.id for c in document.chunks]
                get_vector_store().remove(old_ids)
                get_bm25_index().remove(old_ids)
                for old in list(document.chunks):
                    session.delete(old)
                session.flush()

            chunk_rows = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=c.index,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    content=c.content,
                    char_count=c.char_count,
                )
                for c in chunks
            ]
            session.add_all(chunk_rows)
            session.flush()  # assigns chunk ids

            # --- 5. Embeddings ---------------------------------------------------
            progress("embedding", 70)
            document.processing_stage = "embedding"
            document.processing_progress = 70
            session.commit()

            provider = get_embedding_provider()
            texts = [c.content for c in chunks]
            vectors = provider.embed_texts(texts)

            # --- 6. Vector store + BM25 -------------------------------------------
            progress("indexing", 88)
            document.processing_stage = "indexing"
            document.processing_progress = 88
            session.commit()

            store = get_vector_store()
            db_ids = [row.id for row in chunk_rows]
            store.add(db_ids, vectors)
            for position, row in enumerate(chunk_rows):
                row.vector_position = position
                row.embedding_provider = provider.name

            bm25 = get_bm25_index()
            for row in chunk_rows:
                bm25.upsert(row.id, row.content)

            # --- 7. Done -------------------------------------------------------------
            document.status = DocumentStatus.completed
            document.processing_stage = "completed"
            document.processing_progress = 100
            document.processing_completed_at = datetime.now(timezone.utc)
            session.commit()

            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Ingestion complete doc_id=%d chunks=%d pages=%d chars=%d provider=%s elapsed_ms=%.0f",
                document.id, len(chunk_rows), document.page_count, document.char_count,
                provider.name, elapsed_ms,
            )
            result = {
                "document_id": document.id,
                "chunks": len(chunk_rows),
                "pages": document.page_count,
                "chars": document.char_count,
                "embedding_provider": provider.name,
                "elapsed_ms": round(elapsed_ms, 1),
                "ocr_used": bool(parsed.ocr_attempted),
            }
            progress("completed", 100)
            return result

        except Exception as exc:  # noqa: BLE001
            document.status = DocumentStatus.failed
            document.processing_stage = "failed"
            document.error_message = str(exc)[:800]
            document.processing_completed_at = datetime.now(timezone.utc)
            session.commit()
            logger.error("Ingestion failed doc_id=%d error=%s", document_id, exc)
            if isinstance(exc, DocumentProcessingError):
                raise
            raise DocumentProcessingError(str(exc)) from exc


def submit_document_processing(document_id: int) -> str:
    """Queue ingestion as a background job; returns the job id.

    Live progress is written to the Document row by ``process_document_sync``
    itself; the job registry adds queue/run status on top.
    """
    from app.services.jobs import get_job_registry

    job_id = f"doc-{document_id}-{int(time.time() * 1000)}"

    def _work(progress: ProgressFn) -> None:
        result = process_document_sync(document_id, progress)
        get_job_registry().set_result(job_id, **result)

    get_job_registry().submit(job_id, "document_ingestion", _work)
    return job_id

