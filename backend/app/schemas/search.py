from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    document_ids: Optional[List[int]] = None
    category: Optional[str] = None
    department: Optional[str] = None
    author: Optional[str] = None
    date_from: Optional[str] = None  # ISO date
    date_to: Optional[str] = None
    tags: Optional[List[str]] = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    top_k: int = Field(default=8, ge=1, le=25)
    filters: Optional[SearchFilters] = None


class SearchHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    filename: str
    page_start: int
    page_end: int
    score: float
    sources: List[str]
    snippet: str
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    query: str
    mode: str
    took_ms: float
    total: int
    hits: List[SearchHit]
    embedding_provider: str
    filters_applied: Dict[str, Any] = {}
