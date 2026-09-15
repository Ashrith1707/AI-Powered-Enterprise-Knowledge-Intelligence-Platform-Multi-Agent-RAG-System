"""Agent base class + pipeline context (Module 6 foundation).

Every agent:
* has a clear responsibility, typed input (the shared context) and typed
  output (stored on the context + summarized in the trace);
* executes with timing, timeout, error handling and structured logging;
* records a SAFE execution summary in the trace (never chain-of-thought);
* passes results to the next agent through :class:`PipelineContext`.
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.schemas import (
    AgentStatus,
    AgentStep,
    AgentTrace,
    CompressedContext,
    GeneratedAnswer,
    MetadataDecision,
    Plan,
    RankedChunk,
    RetrievedChunk,
    VerificationResult,
    CitationValidationResult,
    utcnow,
)
from app.config import get_settings
from app.core.errors import AIProviderError
from app.core.logging_conf import get_logger, log_agent_event

logger = get_logger("agents")


@dataclass
class UserInfo:
    id: int
    email: str
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class PipelineContext:
    """Shared state flowing through the agent pipeline."""

    request_id: str
    user: UserInfo
    query: str
    conversation_id: Optional[int] = None
    memory_summary: str = ""
    memory_messages: List[dict] = field(default_factory=list)

    # Authorization: chunk ids the user may retrieve (enforced at retrieval).
    authorized_chunk_ids: Optional[List[int]] = None
    authorized_document_ids: List[int] = field(default_factory=list)

    # Agent outputs (filled as the pipeline progresses)
    plan: Optional[Plan] = None
    metadata_decision: Optional[MetadataDecision] = None
    candidates: List[RetrievedChunk] = field(default_factory=list)
    ranked: List[RankedChunk] = field(default_factory=list)
    compressed: Optional[CompressedContext] = None
    answer: Optional[GeneratedAnswer] = None
    verification: Optional[VerificationResult] = None
    citation_validation: Optional[CitationValidationResult] = None

    trace: AgentTrace = field(default_factory=AgentTrace)
    started_at: float = field(default_factory=time.perf_counter)
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Template-method agent with execution state, timing and tracing."""

    name: str = "base"
    description: str = ""
    timeout_seconds: Optional[float] = None  # None ⇒ settings.agent_timeout_default

    def __init__(self) -> None:
        self._settings = get_settings()

    # -- public entrypoint ---------------------------------------------------
    async def execute(self, ctx: PipelineContext) -> AgentStep:
        step = AgentStep(agent=self.name, status=AgentStatus.running, started_at=utcnow())
        started = time.perf_counter()
        timeout = self.timeout_seconds or self._settings.agent_timeout_default
        try:
            summary, stats = await asyncio.wait_for(self.run(ctx), timeout=timeout)
            step.status = AgentStatus.completed
            step.summary = summary
            step.stats = stats or {}
        except asyncio.TimeoutError:
            step.status = AgentStatus.failed
            step.summary = f"{self.name} timed out after {timeout:.0f}s"
            step.error = {"code": "timeout", "message": step.summary, "retryable": True}
            logger.error("agent=%s status=timeout timeout=%.0fs request_id=%s", self.name, timeout, ctx.request_id)
        except AIProviderError as exc:
            step.status = AgentStatus.failed
            step.summary = exc.message
            step.error = {
                "code": exc.error_code.value,
                "message": exc.message,
                "retryable": exc.retryable,
                **( {"model": exc.model} if exc.model else {} ),
            }
            # propagate provider errors: the orchestrator decides recovery
            step.duration_ms = (time.perf_counter() - started) * 1000
            ctx.trace.add(step)
            log_agent_event(logger, agent=self.name, status="failed", code=exc.error_code.value,
                            duration_ms=round(step.duration_ms, 1), request_id=ctx.request_id)
            raise
        except Exception as exc:  # noqa: BLE001
            step.status = AgentStatus.failed
            step.summary = f"{self.name} failed: {type(exc).__name__}"
            step.error = {"code": "agent_error", "message": str(exc)[:300], "retryable": False}
            logger.exception("agent=%s failed request_id=%s", self.name, ctx.request_id)
        step.duration_ms = (time.perf_counter() - started) * 1000
        ctx.trace.add(step)
        log_agent_event(
            logger,
            agent=self.name,
            status=step.status.value,
            duration_ms=round(step.duration_ms, 1),
            request_id=ctx.request_id,
            **{k: v for k, v in (step.stats or {}).items() if isinstance(v, (int, float, str, bool))},
        )
        return step

    def skip(self, ctx: PipelineContext, reason: str) -> AgentStep:
        step = AgentStep(agent=self.name, status=AgentStatus.skipped, started_at=utcnow(), summary=reason)
        ctx.trace.add(step)
        log_agent_event(logger, agent=self.name, status="skipped", reason=reason, request_id=ctx.request_id)
        return step

    # -- agent implementation -------------------------------------------------
    @abstractmethod
    async def run(self, ctx: PipelineContext) -> tuple[str, Dict[str, Any]]:
        """Do the work, mutate ``ctx``, and return (safe_summary, stats)."""
