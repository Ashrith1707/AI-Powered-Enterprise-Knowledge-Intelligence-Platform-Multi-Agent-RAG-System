"""Structured agent inputs/outputs and trace schemas (Module 6).

Every agent produces a typed, serializable output. The trace contains only
*safe execution summaries* — never hidden chain-of-thought or raw prompts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class AgentStep(BaseModel):
    """One entry in the agent trace."""

    agent: str
    status: AgentStatus = AgentStatus.pending
    started_at: Optional[datetime] = None
    duration_ms: float = 0.0
    summary: str = ""                      # safe, user-visible summary
    stats: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None  # {"code", "message", "retryable"}


class AgentTrace(BaseModel):
    request_id: str = ""
    steps: List[AgentStep] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = True

    def add(self, step: AgentStep) -> None:
        self.steps.append(step)

    def step(self, agent: str) -> Optional[AgentStep]:
        return next((s for s in reversed(self.steps) if s.agent == agent), None)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
class Plan(BaseModel):
    intent: str = "knowledge_retrieval"  # knowledge_retrieval | conversational | analytics | metadata_lookup
    requires_retrieval: bool = True
    requires_metadata_filter: bool = False
    strategy: str = "hybrid"             # hybrid | vector | keyword
    top_k: int = 8
    sub_queries: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str = ""          # one-line safe summary


# ---------------------------------------------------------------------------
# Retrieval / metadata
# ---------------------------------------------------------------------------
class RetrievedChunk(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str = ""
    filename: str = ""
    page_start: int = 1
    page_end: int = 1
    content: str
    score: float = 0.0
    sources: List[str] = Field(default_factory=list)  # vector | keyword
    vector_rank: Optional[int] = None
    vector_score: Optional[float] = None
    keyword_rank: Optional[int] = None
    keyword_score: Optional[float] = None
    matched_queries: List[str] = Field(default_factory=list)


class MetadataDecision(BaseModel):
    applied_filters: Dict[str, Any] = Field(default_factory=dict)
    matched_document_ids: Optional[List[int]] = None  # None ⇒ no metadata filtering applied
    authorized_document_ids: List[int] = Field(default_factory=list)
    total_documents: int = 0
    matched_documents: int = 0
    notes: str = ""
    fell_back_to_unfiltered: bool = False


class RankedChunk(RetrievedChunk):
    rerank_score: float = 0.0
    rerank_method: str = ""


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------
class Evidence(BaseModel):
    evidence_id: str                       # "E1", "E2", ...
    chunk_id: int
    document_id: int
    document_title: str
    filename: str
    page_start: int
    page_end: int
    text: str
    score: float
    original_chars: int
    compressed_chars: int


class CompressedContext(BaseModel):
    evidences: List[Evidence] = Field(default_factory=list)
    total_chars: int = 0
    budget_chars: int = 0
    removed_duplicates: int = 0
    removed_low_relevance: int = 0
    chars_before: int = 0


# ---------------------------------------------------------------------------
# Generation / verification / citations
# ---------------------------------------------------------------------------
class GeneratedAnswer(BaseModel):
    text: str
    insufficient_evidence: bool = False
    model: str = ""
    provider: str = ""
    streamed: bool = False
    latency_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    regeneration_attempt: int = 0


class ClaimCheck(BaseModel):
    claim: str
    supported: bool
    support_score: float
    best_evidence: List[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    verified: bool = False
    confidence: float = 0.0
    unsupported_claims: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    evidence_coverage: float = 0.0
    supported_ratio: float = 0.0
    method: str = "lexical-entailment-v1"
    claim_checks: List[ClaimCheck] = Field(default_factory=list)


class Citation(BaseModel):
    citation_id: str                       # "C1", ...
    evidence_id: str                       # "E1", ...
    document_id: int
    document_title: str
    filename: str
    page_start: int
    page_end: int
    chunk_id: int
    quote: str = ""


class CitationValidationResult(BaseModel):
    cleaned_text: str
    valid_citations: List[Citation] = Field(default_factory=list)
    removed_citations: List[Dict[str, Any]] = Field(default_factory=list)
    citations_found: int = 0
    citations_valid: int = 0
    uncited_sentences: int = 0


# ---------------------------------------------------------------------------
# Final response
# ---------------------------------------------------------------------------
class ResponseMetrics(BaseModel):
    total_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0
    verification_latency_ms: float = 0.0
    chunks_retrieved: int = 0
    chunks_after_rerank: int = 0
    evidences_used: int = 0
    top_k: int = 0
    token_usage: Dict[str, Any] = Field(default_factory=dict)
    verification_failures: int = 0
    regenerations: int = 0
    embedding_provider: str = ""
    llm_provider: str = ""


class FinalResponse(BaseModel):
    answer: str
    insufficient_evidence: bool = False
    citations: List[Citation] = Field(default_factory=list)
    verification: VerificationResult
    plan: Plan
    trace: AgentTrace
    metrics: ResponseMetrics
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    degraded: bool = False
    error: Optional[Dict[str, Any]] = None
    ai_mode: str = ""                      # "gemini" | "mock" (+ embedding provider)
