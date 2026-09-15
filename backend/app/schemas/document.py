from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    page_count: int = 0
    char_count: int = 0
    ocr_used: bool = False
    metadata: Dict[str, Any] = {}
    entities: Dict[str, Any] = {}
    chunk_count: int = 0
    processing_stage: Optional[str] = None
    processing_progress: int = 0
    created_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    owner_email: Optional[str] = None

    @classmethod
    def from_model(cls, doc) -> "DocumentOut":
        return cls(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            error_message=doc.error_message,
            page_count=doc.page_count,
            char_count=doc.char_count,
            ocr_used=bool(doc.ocr_used),
            metadata=doc.metadata_json or {},
            entities=doc.entities_json or {},
            chunk_count=len(doc.chunks) if doc.chunks is not None else 0,
            processing_stage=doc.processing_stage,
            processing_progress=doc.processing_progress or 0,
            created_at=doc.created_at,
            processing_started_at=doc.processing_started_at,
            processing_completed_at=doc.processing_completed_at,
            owner_email=getattr(doc.owner, "email", None),
        )


class DocumentListOut(BaseModel):
    items: List[DocumentOut]
    total: int
    page: int
    page_size: int


class DocumentStatusOut(BaseModel):
    document_id: int
    status: str
    stage: Optional[str] = None
    progress: int = 0
    error_message: Optional[str] = None
    job: Optional[Dict[str, Any]] = None


class DocumentContentPage(BaseModel):
    page: int
    text: str


class DocumentContentOut(BaseModel):
    document_id: int
    filename: str
    pages: List[DocumentContentPage]
