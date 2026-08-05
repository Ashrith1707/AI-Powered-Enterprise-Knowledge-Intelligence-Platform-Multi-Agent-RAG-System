"""All database access for documents, pages and metadata.

Services never touch SQLAlchemy directly — they go through this layer,
which keeps persistence swappable and unit-testable.
"""
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Document, Page, DocumentMetadata


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> Document:
        doc = Document(**fields)
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get(self, document_id: int) -> Document | None:
        return self.db.get(Document, document_id)

    def get_by_checksum(self, checksum: str) -> Document | None:
        return self.db.scalar(select(Document).where(Document.checksum == checksum))

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Document]:
        stmt = (select(Document).order_by(Document.uploaded_at.desc())
                .limit(limit).offset(offset))
        return list(self.db.scalars(stmt))

    def set_status(self, doc: Document, status: str, error: str | None = None) -> Document:
        doc.status = status
        doc.error_message = error
        if status in ("parsed", "indexed", "failed"):
            doc.processed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def add_pages(self, doc: Document, pages: list[dict]) -> None:
        for p in pages:
            self.db.add(Page(document_id=doc.id, **p))
        doc.page_count = len(pages)
        self.db.commit()

    def get_pages(self, document_id: int) -> list[Page]:
        stmt = (select(Page).where(Page.document_id == document_id)
                .order_by(Page.page_number))
        return list(self.db.scalars(stmt))

    def save_metadata(self, doc: Document, **fields) -> DocumentMetadata:
        meta = self.db.scalar(
            select(DocumentMetadata).where(DocumentMetadata.document_id == doc.id))
        if meta is None:
            meta = DocumentMetadata(document_id=doc.id)
            self.db.add(meta)
        for key, value in fields.items():
            setattr(meta, key, value)
        self.db.commit()
        self.db.refresh(meta)
        return meta

    def delete(self, doc: Document) -> None:
        self.db.delete(doc)
        self.db.commit()

    def counts_by_status(self) -> dict[str, int]:
        rows = self.db.execute(
            select(Document.status, func.count()).group_by(Document.status)).all()
        return {status: count for status, count in rows}

    def counts_by(self, column) -> dict[str, int]:
        rows = self.db.execute(select(column, func.count()).group_by(column)).all()
        return {key: count for key, count in rows}

    def total_pages(self) -> int:
        return self.db.scalar(select(func.count(Page.id))) or 0
