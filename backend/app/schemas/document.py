"""Request/response contracts for the document APIs."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MetadataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    author: str
    language: str
    keywords: list[str]
    entities: dict
    summary: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    category: str
    description: str = ""
    tags: list[str] = []
    page_count: int
    used_ocr: bool
    uploaded_at: datetime
    processed_at: datetime | None = None
    error_message: str | None = None


class DocumentPatch(BaseModel):
    filename: str | None = Field(default=None, min_length=1, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None


class DocumentDetailOut(DocumentOut):
    doc_metadata: MetadataOut | None = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    page_number: int
    text: str
    ocr_applied: bool
    word_count: int


class UploadResponse(BaseModel):
    document: DocumentOut
    message: str
