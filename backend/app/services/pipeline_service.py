"""Document ingestion pipeline (Phase 1 core).

upload -> parse (+OCR) -> clean -> pages -> metadata -> classify -> persist -> index

Runs as a FastAPI background task so the upload API returns immediately.
Every stage transition is written to the documents.status column and to
the audit log, so the frontend can poll progress.
"""
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.repositories.activity_repository import ActivityRepository
from app.repositories.document_repository import DocumentRepository
from app.services.classification_service import ClassificationService
from app.services.metadata_service import MetadataService
from app.services.parsing_service import ParsingService

logger = get_logger("pipeline")


class PipelineService:
    def __init__(self, db: Session):
        self.db = db
        self.docs = DocumentRepository(db)
        self.activity = ActivityRepository(db)
        self.parser = ParsingService()
        self.metadata = MetadataService()
        self.classifier = ClassificationService()

    def process(self, document_id: int) -> None:
        doc = self.docs.get(document_id)
        if doc is None:
            logger.error("Pipeline called for missing document %d", document_id)
            return
        try:
            self.docs.set_status(doc, "parsing")

            pages, used_ocr = self.parser.parse(doc.stored_path, doc.file_type)
            doc.used_ocr = used_ocr
            self.docs.add_pages(doc, pages)

            meta = self.metadata.extract(doc.filename, pages)
            self.docs.save_metadata(doc, **meta)

            doc.category = self.classifier.classify(pages, meta["keywords"])
            self.docs.set_status(doc, "parsed")

            # Phase 3 hook: chunk + embed + FAISS
            from app.rag.rag_service import RAGService
            chunk_count = RAGService(self.db).index_document(doc.id, pages)

            self.docs.set_status(doc, "indexed")
            self.activity.audit("pipeline", "document.processed", "document", doc.id,
                                {"pages": len(pages), "chunks": chunk_count,
                                 "ocr": used_ocr, "category": doc.category})
            logger.info("Document %d processed: %d pages, %d chunks.",
                        doc.id, len(pages), chunk_count)
        except Exception as exc:
            logger.exception("Pipeline failed for document %d", document_id)
            self.docs.set_status(doc, "failed", error=str(exc))
            self.activity.audit("pipeline", "document.failed", "document",
                                doc.id, {"error": str(exc)})
