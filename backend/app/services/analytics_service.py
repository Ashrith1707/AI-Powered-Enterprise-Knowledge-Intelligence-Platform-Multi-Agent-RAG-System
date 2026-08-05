"""Aggregates platform metrics for the dashboard and reports."""
from sqlalchemy.orm import Session

from app.models import Document
from app.repositories.activity_repository import ActivityRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository


class AnalyticsService:
    def __init__(self, db: Session):
        self.docs = DocumentRepository(db)
        self.chunks = ChunkRepository(db)
        self.activity = ActivityRepository(db)

    def dashboard_stats(self) -> dict:
        by_status = self.docs.counts_by_status()
        total_searches, avg_latency = self.activity.search_stats()
        return {
            "total_documents": sum(by_status.values()),
            "indexed_documents": by_status.get("indexed", 0),
            "failed_documents": by_status.get("failed", 0),
            "total_pages": self.docs.total_pages(),
            "total_chunks": self.chunks.count(),
            "total_searches": total_searches,
            "avg_latency_ms": avg_latency,
            "documents_by_category": self.docs.counts_by(Document.category),
            "documents_by_type": self.docs.counts_by(Document.file_type),
            "recent_queries": self.activity.recent_queries(),
        }
