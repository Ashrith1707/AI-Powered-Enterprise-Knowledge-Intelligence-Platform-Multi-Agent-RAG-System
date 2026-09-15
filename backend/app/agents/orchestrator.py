"""Centralized agent orchestration layer (Module 6).

Pipeline (matches the target architecture):

    Planner → (Retriever ∥ Metadata) → merge → Reranker → Compressor
            → Generator → Verifier (bounded retry) → Citation Validator
            → FinalResponse

Also handles: execution state (PipelineContext), agent trace, retry policy
(max_regeneration_attempts — no infinite loops), per-agent timeouts, failure
recovery (classified AI errors surface to the client instead of being
masked), persistence (messages, citations, trace, metrics), memory
summarization and audit logging.

ONE orchestrator — there is no second competing agent framework in this repo.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.answer_generator import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    AnswerGeneratorAgent,
    build_prompt,
    SYSTEM_PROMPT,
)
from app.agents.base import BaseAgent, PipelineContext, UserInfo
from app.agents.citation_validator import CitationValidationAgent
from app.agents.compressor import ContextCompressionAgent
from app.agents.metadata import MetadataAgent, compute_authorized_ids
from app.agents.planner import PlannerAgent
from app.agents.reranker import RerankerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.schemas import (
    AgentStep,
    AgentStatus,
    AgentTrace,
    FinalResponse,
    GeneratedAnswer,
    ResponseMetrics,
    VerificationResult,
    utcnow,
)
from app.agents.verifier import VerificationAgent
from app.config import get_settings
from app.core.errors import AIProviderError, classify_ai_error
from app.core.logging_conf import get_logger, log_agent_event
from app.core.middleware import record_latency, record_metric
from app.memory.conversation_memory import build_memory_context, maybe_summarize_conversation
from app.models import AuditLog, Conversation, Document, DocumentChunk, Message

logger = get_logger("orchestrator")

AGENT_ORDER = [
    "planner", "retriever", "metadata", "reranker",
    "compressor", "answer_generator", "verifier", "citation_validator",
]


class AgentOrchestrator:
    def __init__(self) -> None:
        self.planner = PlannerAgent()
        self.retriever = RetrieverAgent()
        self.metadata = MetadataAgent()
        self.reranker = RerankerAgent()
        self.compressor = ContextCompressionAgent()
        self.generator = AnswerGeneratorAgent()
        self.verifier = VerificationAgent()
        self.citation_validator = CitationValidationAgent()
        self._agents: Dict[str, BaseAgent] = {
            a.name: a for a in (
                self.planner, self.retriever, self.metadata, self.reranker,
                self.compressor, self.generator, self.verifier, self.citation_validator,
            )
        }

    # ------------------------------------------------------------------
    # Non-streaming execution
    # ------------------------------------------------------------------
    async def run(
        self,
        session: Session,
        user: UserInfo,
        query: str,
        conversation_id: Optional[int] = None,
        request_id: str = "",
        return_context: bool = False,
    ):
        ctx = await self._prepare(session, user, query, conversation_id, request_id)
        started = time.perf_counter()
        provider_error: Optional[AIProviderError] = None

        try:
            await self._execute_core(ctx)
        except AIProviderError as exc:
            provider_error = exc
            logger.error("Pipeline provider error request_id=%s code=%s", ctx.request_id, exc.error_code.value)

        if provider_error is None:
            await self._verify_and_finalize(ctx)

        total_ms = (time.perf_counter() - started) * 1000
        response = self._build_response(ctx, total_ms, provider_error)
        await asyncio.to_thread(
            self._persist, session, ctx, response
        )
        record_latency("agent_pipeline", total_ms / 1000)
        record_metric("chat_requests")
        if provider_error:
            record_metric("chat_provider_errors")
        if return_context:
            return response, ctx
        return response

    # ------------------------------------------------------------------
    # Streaming execution (SSE events)
    # ------------------------------------------------------------------
    async def run_stream(
        self,
        session: Session,
        user: UserInfo,
        query: str,
        conversation_id: Optional[int] = None,
        request_id: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        ctx = await self._prepare(session, user, query, conversation_id, request_id)
        started = time.perf_counter()

        try:
            async for event in self._execute_core_streaming(ctx):
                yield event
        except AIProviderError as exc:
            yield {
                "event": "error",
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
            response = self._build_response(ctx, (time.perf_counter() - started) * 1000, exc)
            await asyncio.to_thread(self._persist, session, ctx, response)
            record_metric("chat_provider_errors")
            return

        await self._verify_and_finalize_streaming(ctx)
        for name in ("verifier", "citation_validator"):
            step = ctx.trace.step(name)
            if step is not None:
                yield {"event": "trace", "step": step.model_dump(mode="json")}
        total_ms = (time.perf_counter() - started) * 1000
        response = self._build_response(ctx, total_ms, None)
        await asyncio.to_thread(self._persist, session, ctx, response)
        record_latency("agent_pipeline", total_ms / 1000)
        record_metric("chat_requests")
        yield {"event": "final", "response": response.model_dump(mode="json")}

    # ------------------------------------------------------------------
    # Preparation
    # ------------------------------------------------------------------
    async def _prepare(
        self,
        session: Session,
        user: UserInfo,
        query: str,
        conversation_id: Optional[int],
        request_id: str,
    ) -> PipelineContext:
        ctx = PipelineContext(request_id=request_id or f"req-{int(time.time()*1000)}", user=user, query=query)

        conversation: Optional[Conversation] = None
        if conversation_id:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None or (conversation.user_id != user.id and not user.is_admin):
                conversation = None
                conversation_id = None
        if conversation is None:
            conversation = Conversation(user_id=user.id, title=_title_from_query(query))
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
        ctx.conversation_id = conversation.id

        memory = build_memory_context(session, conversation)
        ctx.memory_summary = memory.summary
        ctx.memory_messages = memory.recent_messages

        doc_ids, chunk_ids = await asyncio.to_thread(compute_authorized_ids, session, user.id, user.is_admin)
        ctx.authorized_document_ids = doc_ids
        ctx.authorized_chunk_ids = chunk_ids
        ctx.trace = AgentTrace(request_id=ctx.request_id)
        return ctx

    # ------------------------------------------------------------------
    # Core pipeline (non-streaming)
    # ------------------------------------------------------------------
    async def _execute_core(self, ctx: PipelineContext) -> None:
        await self.planner.execute(ctx)
        plan = ctx.plan or _safe_default_plan()
        ctx.plan = plan

        if plan.intent == "conversational":
            self._canned_conversational(ctx)
            return
        if plan.intent == "analytics":
            await self._canned_analytics(ctx)
            return

        # Retriever and Metadata agents run in parallel (per architecture);
        # retrieval is authorization-scoped, metadata filtering is merged after.
        await asyncio.gather(self.retriever.execute(ctx), self.metadata.execute(ctx))
        _reorder_parallel_trace(ctx)
        self._apply_metadata_filter(ctx)

        await self.reranker.execute(ctx)
        await self.compressor.execute(ctx)
        await self.generator.execute(ctx)

    async def _execute_core_streaming(self, ctx: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        step = await self.planner.execute(ctx)
        yield {"event": "trace", "step": step.model_dump(mode="json")}
        plan = ctx.plan or _safe_default_plan()
        ctx.plan = plan
        yield {"event": "plan", "plan": plan.model_dump(mode="json")}

        if plan.intent in ("conversational", "analytics"):
            if plan.intent == "conversational":
                self._canned_conversational(ctx)
            else:
                await self._canned_analytics(ctx)
            for name in ("retriever", "metadata", "reranker", "compressor"):
                sk = self._agents[name].skip(ctx, f"Skipped — intent '{plan.intent}' does not require retrieval.")
                yield {"event": "trace", "step": sk.model_dump(mode="json")}
            text = ctx.answer.text if ctx.answer else ""
            yield {"event": "token", "delta": text}
            return

        # Parallel retrieval + metadata
        steps = await asyncio.gather(self.retriever.execute(ctx), self.metadata.execute(ctx))
        _reorder_parallel_trace(ctx)
        for st in steps:
            yield {"event": "trace", "step": st.model_dump(mode="json")}
        self._apply_metadata_filter(ctx)

        for agent in (self.reranker, self.compressor):
            st = await agent.execute(ctx)
            yield {"event": "trace", "step": st.model_dump(mode="json")}

        # Generator: stream tokens when the evidence supports an answer.
        gen_step = AgentStep(agent="answer_generator", status=AgentStatus.running, started_at=utcnow())
        t0 = time.perf_counter()
        compressed = ctx.compressed
        if not compressed or not compressed.evidences:
            st = await self.generator.execute(ctx)
            yield {"event": "trace", "step": st.model_dump(mode="json")}
            yield {"event": "token", "delta": ctx.answer.text if ctx.answer else INSUFFICIENT_EVIDENCE_ANSWER}
            return

        from app.services.llm import get_llm_provider
        provider = get_llm_provider()
        prompt = build_prompt(ctx, compressed)
        chunks_text: List[str] = []
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()

        def _produce() -> None:
            try:
                for piece in provider.generate_stream(prompt, system_instruction=SYSTEM_PROMPT):
                    loop.call_soon_threadsafe(queue.put_nowait, piece)
            except BaseException as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        worker = asyncio.get_running_loop().run_in_executor(None, _produce)
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                await worker
                gen_step.duration_ms = (time.perf_counter() - t0) * 1000
                raise classify_ai_error(item) if not isinstance(item, AIProviderError) else item
            chunks_text.append(item)
            yield {"event": "token", "delta": item}
        await worker

        text = "".join(chunks_text).strip() or INSUFFICIENT_EVIDENCE_ANSWER
        ctx.answer = GeneratedAnswer(
            text=text,
            insufficient_evidence=(text == INSUFFICIENT_EVIDENCE_ANSWER),
            model=getattr(provider, "model", "mock-extractive-v1"),
            provider=provider.name,
            streamed=True,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
        gen_step.status = AgentStatus.completed
        gen_step.duration_ms = (time.perf_counter() - t0) * 1000
        gen_step.summary = (
            f"Streamed {len(text.split())}-word answer via {provider.name} "
            f"({ctx.answer.model}) in {gen_step.duration_ms:.0f}ms."
        )
        gen_step.stats = {
            "provider": provider.name, "model": ctx.answer.model,
            "words": len(text.split()), "latency_ms": round(gen_step.duration_ms, 1), "streamed": True,
        }
        ctx.trace.add(gen_step)
        yield {"event": "trace", "step": gen_step.model_dump(mode="json")}

    # ------------------------------------------------------------------
    # Verification with bounded retry + citation validation
    # ------------------------------------------------------------------
    async def _verify_and_finalize(self, ctx: PipelineContext) -> None:
        settings = get_settings()
        await self.verifier.execute(ctx)

        attempts = 0
        while (
            ctx.verification is not None
            and not ctx.verification.verified
            and ctx.answer is not None
            and not ctx.answer.insufficient_evidence
            and not ctx.extra.get("canned_response")
            and attempts < settings.max_regeneration_attempts
            and ctx.compressed is not None
            and ctx.compressed.evidences
        ):
            attempts += 1
            record_metric("verification_failures")
            logger.warning(
                "Verification failed request_id=%s unsupported=%d — regeneration attempt %d/%d",
                ctx.request_id, len(ctx.verification.unsupported_claims), attempts,
                settings.max_regeneration_attempts,
            )
            ctx.extra["regeneration"] = attempts
            await self.generator.execute(ctx)
            await self.verifier.execute(ctx)

        if (
            ctx.verification is not None
            and not ctx.verification.verified
            and ctx.answer is not None
            and not ctx.answer.insufficient_evidence
            and not ctx.extra.get("canned_response")
        ):
            # Safe fallback: never ship an unverified answer as if it were grounded.
            ctx.extra["regeneration_exhausted"] = True
            record_metric("verification_fallbacks")
            ctx.answer.text = (
                INSUFFICIENT_EVIDENCE_ANSWER
                + " (A draft answer could not be verified against the retrieved evidence and was withheld.)"
            )
            ctx.answer.insufficient_evidence = True
            ctx.verification = VerificationResult(
                verified=True, confidence=1.0,
                method="safe-fallback-after-verification-failure",
                supported_ratio=1.0,
                unsupported_claims=ctx.verification.unsupported_claims,
            )

        await self.citation_validator.execute(ctx)

    async def _verify_and_finalize_streaming(self, ctx: PipelineContext) -> None:
        """Streaming path: tokens were already delivered, so verification runs
        post-hoc. No regeneration (would duplicate streamed content); the
        final event carries the verification verdict and the frontend shows
        it. If verification fails badly, the persisted answer is annotated."""
        if ctx.extra.get("canned_response") or (ctx.answer and ctx.answer.insufficient_evidence):
            await self.verifier.execute(ctx)
            await self.citation_validator.execute(ctx)
            return

        await self.verifier.execute(ctx)
        if ctx.verification is not None and not ctx.verification.verified:
            record_metric("verification_failures")
            note = (
                "\n\n⚠️ Verification notice: parts of this answer could not be fully "
                "confirmed against the retrieved evidence (confidence "
                f"{ctx.verification.confidence:.0%}). Please review the cited sources."
            )
            if ctx.answer is not None:
                ctx.answer.text += note
        await self.citation_validator.execute(ctx)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_metadata_filter(self, ctx: PipelineContext) -> None:
        decision = ctx.metadata_decision
        if decision is None or decision.matched_document_ids is None:
            return
        allowed = set(decision.matched_document_ids)
        before = len(ctx.candidates)
        filtered = [c for c in ctx.candidates if c.document_id in allowed]
        if filtered:
            ctx.candidates = filtered
            ctx.extra["metadata_filtered"] = {"before": before, "after": len(filtered)}
        # If filtering empties the result set, the Metadata Agent already
        # decided on the honest fallback (matched_document_ids=None).

    def _canned_conversational(self, ctx: PipelineContext) -> None:
        ctx.extra["canned_response"] = True
        for name in ("retriever", "metadata", "reranker", "compressor"):
            self._agents[name].skip(ctx, f"Skipped — intent 'conversational' does not require retrieval.")
        ctx.answer = GeneratedAnswer(
            text=(
                "Hello! I'm KnowledgeIQ, your enterprise knowledge assistant. Ask me anything about "
                "your uploaded documents — for example \"What are the safety requirements for machine "
                "maintenance?\" — and I'll answer with citations to the exact pages."
            ),
            model="none", provider="system",
        )

    async def _canned_analytics(self, ctx: PipelineContext) -> None:
        ctx.extra["canned_response"] = True
        for name in ("retriever", "metadata", "reranker", "compressor"):
            self._agents[name].skip(ctx, "Skipped — analytics intent answered from system statistics.")
        stats = await asyncio.to_thread(self._system_stats, ctx)
        lines = [
            "Here is a snapshot of your KnowledgeIQ workspace:",
            f"- Documents indexed: {stats['documents_completed']} (of {stats['documents_total']} total)",
            f"- Text chunks in the vector index: {stats['chunks']}",
            f"- Conversations: {stats['conversations']}; questions asked: {stats['questions']}",
        ]
        if stats["recent_uploads"]:
            lines.append("- Recent uploads: " + ", ".join(stats["recent_uploads"]))
        lines.append("\nYou can see detailed charts on the Analytics page.")
        ctx.answer = GeneratedAnswer(text="\n".join(lines), model="none", provider="system")

    def _system_stats(self, ctx: PipelineContext) -> Dict[str, Any]:
        from app.database import get_session_factory
        from app.models import Conversation as Conv

        session: Session = get_session_factory()()
        try:
            scope = {} if ctx.user.is_admin else {"user_id": ctx.user.id}
            docs_q = select(func.count(Document.id)).filter_by(**scope)
            total = session.execute(docs_q).scalar() or 0
            completed = session.execute(
                select(func.count(Document.id)).filter_by(**scope, status="completed")
            ).scalar() or 0
            doc_ids = [
                row[0] for row in session.execute(select(Document.id).filter_by(**scope)).all()
            ]
            chunks = 0
            if doc_ids:
                chunks = session.execute(
                    select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id.in_(doc_ids))
                ).scalar() or 0
            conversations = session.execute(
                select(func.count(Conv.id)).filter_by(**scope)
            ).scalar() or 0
            conv_ids = [row[0] for row in session.execute(select(Conv.id).filter_by(**scope)).all()]
            questions = 0
            if conv_ids:
                questions = session.execute(
                    select(func.count(Message.id)).where(
                        Message.conversation_id.in_(conv_ids), Message.role == "user"
                    )
                ).scalar() or 0
            recent = session.execute(
                select(Document.filename).filter_by(**scope).order_by(Document.created_at.desc()).limit(3)
            ).scalars().all()
            return {
                "documents_total": total, "documents_completed": completed, "chunks": chunks,
                "conversations": conversations, "questions": questions, "recent_uploads": list(recent),
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Response building
    # ------------------------------------------------------------------
    def _build_response(
        self, ctx: PipelineContext, total_ms: float, error: Optional[AIProviderError]
    ) -> FinalResponse:
        trace = ctx.trace
        trace.total_duration_ms = round(total_ms, 1)
        trace.success = error is None and all(
            s.status in (AgentStatus.completed, AgentStatus.skipped) for s in trace.steps
        )

        def step_ms(name: str) -> float:
            step = trace.step(name)
            return round(step.duration_ms, 1) if step else 0.0

        answer = ctx.answer
        verification = ctx.verification or VerificationResult(verified=False, confidence=0.0)
        citations = ctx.citation_validation.valid_citations if ctx.citation_validation else []

        if error is not None and (answer is None or not answer.text):
            answer_text = ""
        elif error is not None:
            answer_text = answer.text if answer else ""
        else:
            answer_text = answer.text if answer else INSUFFICIENT_EVIDENCE_ANSWER

        metrics = ResponseMetrics(
            total_latency_ms=round(total_ms, 1),
            retrieval_latency_ms=step_ms("retriever"),
            generation_latency_ms=step_ms("answer_generator"),
            verification_latency_ms=step_ms("verifier"),
            chunks_retrieved=len(ctx.candidates),
            chunks_after_rerank=len(ctx.ranked),
            evidences_used=len(ctx.compressed.evidences) if ctx.compressed else 0,
            top_k=ctx.plan.top_k if ctx.plan else 0,
            token_usage={
                "prompt_tokens": answer.prompt_tokens if answer else None,
                "output_tokens": answer.output_tokens if answer else None,
            },
            verification_failures=int(bool(ctx.extra.get("regeneration"))),
            regenerations=int(ctx.extra.get("regeneration", 0)),
            embedding_provider=ctx.extra.get("embedding_provider", ""),
            llm_provider=answer.provider if answer else "",
        )

        from app.services.embeddings import embedding_provider_status
        from app.services.llm import get_llm_provider

        metrics.embedding_provider = embedding_provider_status()["provider"]
        ai_mode = get_llm_provider().name

        return FinalResponse(
            answer=answer_text,
            insufficient_evidence=bool(answer.insufficient_evidence) if answer else True,
            citations=citations,
            verification=verification,
            plan=ctx.plan or _safe_default_plan(),
            trace=trace,
            metrics=metrics,
            conversation_id=ctx.conversation_id,
            degraded=error is not None,
            error=(
                {"code": error.error_code.value, "message": error.message, "details": error.details}
                if error else None
            ),
            ai_mode=ai_mode,
        )

    # ------------------------------------------------------------------
    # Persistence (runs in a worker thread)
    # ------------------------------------------------------------------
    def _persist(self, session: Session, ctx: PipelineContext, response: FinalResponse) -> None:
        conversation = session.get(Conversation, ctx.conversation_id) if ctx.conversation_id else None
        if conversation is None:
            logger.warning("Cannot persist: conversation %s missing", ctx.conversation_id)
            return

        user_message = Message(conversation_id=conversation.id, role="user", content=ctx.query)
        session.add(user_message)

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response.answer or (response.error or {}).get("message", ""),
            citations_json=[c.model_dump(mode="json") for c in response.citations],
            agent_trace_json=response.trace.model_dump(mode="json"),
            metrics_json=response.metrics.model_dump(mode="json"),
        )
        session.add(assistant_message)
        conversation.updated_at = datetime.now(timezone.utc)
        session.flush()

        session.add(
            AuditLog(
                user_id=ctx.user.id,
                action="ask_ai",
                resource_type="conversation",
                resource_id=str(conversation.id),
                outcome="success" if not response.degraded else "degraded",
                detail_json={
                    "intent": response.plan.intent,
                    "chunks_retrieved": response.metrics.chunks_retrieved,
                    "verified": response.verification.verified,
                    "citations": len(response.citations),
                    "total_latency_ms": response.metrics.total_latency_ms,
                    "degraded": response.degraded,
                },
            )
        )
        session.commit()
        session.refresh(assistant_message)
        response.message_id = assistant_message.id

        maybe_summarize_conversation(session, conversation)
        log_agent_event(
            logger, event="pipeline_complete", request_id=ctx.request_id,
            conversation_id=conversation.id, message_id=assistant_message.id,
            total_ms=response.metrics.total_latency_ms, verified=response.verification.verified,
            citations=len(response.citations), degraded=response.degraded,
        )


def _title_from_query(query: str) -> str:
    title = " ".join(query.split())
    return (title[:57] + "…") if len(title) > 58 else (title or "New conversation")


def _reorder_parallel_trace(ctx: PipelineContext) -> None:
    """Retriever and Metadata run concurrently; present them in a stable,
    architecture-aligned order (retriever, then metadata) in the trace."""
    steps = ctx.trace.steps
    idx_r = next((i for i, s in enumerate(steps) if s.agent == "retriever"), None)
    idx_m = next((i for i, s in enumerate(steps) if s.agent == "metadata"), None)
    if idx_r is not None and idx_m is not None and idx_r > idx_m:
        steps[idx_r], steps[idx_m] = steps[idx_m], steps[idx_r]


def _safe_default_plan():
    """Fallback plan if the Planner itself failed — retrieval still authorized-scoped."""
    from app.agents.schemas import Plan

    return Plan(
        intent="knowledge_retrieval",
        requires_retrieval=True,
        strategy="hybrid",
        top_k=get_settings().retrieval_top_k,
        sub_queries=[],
        reasoning_summary="Planner failed; using safe default retrieval plan.",
    )


_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
