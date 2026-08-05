"""Contracts for semantic search and RAG question answering."""
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    page_number: int
    score: float
    snippet: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    latency_ms: float


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    # Enables conversation-aware retrieval (follow-up resolution) when set.
    conversation_id: int | None = None


class Citation(BaseModel):
    marker: str            # e.g. "[1]"
    document_id: int
    document_name: str
    page_number: int
    snippet: str


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    confidence: float
    latency_ms: float
    agent_trace: list[str] = []
