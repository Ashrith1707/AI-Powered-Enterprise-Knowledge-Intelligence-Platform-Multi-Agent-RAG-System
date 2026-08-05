"""End-to-end RAG pipeline (Module 5: hybrid + agentic).

question -> Planner (analyze/rewrite/expand) -> Retriever (dense+BM25+RRF,
dedup, adaptive selection, stitching, compression) -> sufficiency gate
-> Answerer (adaptive prompt -> Gemini) -> Verifier (groundedness,
calibrated confidence) -> cited answer

Also exposes index_document() used by the ingestion pipeline, so indexing
and answering share one chunk/vector/BM25 representation.
"""
import time

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.rag.advanced_retriever import AdvancedRetriever
from app.rag.bm25 import lexical_index
from app.rag.chunker import Chunker
from app.rag.citation_engine import CitationEngine
from app.rag.embeddings import get_embedder
from app.rag.llm_client import generate
from app.rag.prompt_builder import PromptBuilder
from app.rag.retriever import Retriever
from app.rag.vector_store import get_vector_store
from app.rag.verifier import calibrated_confidence, verify_answer
from app.repositories.chunk_repository import ChunkRepository

logger = get_logger("rag")

REFUSAL = ("The knowledge base does not contain enough information to answer "
           "this. Try uploading relevant documents first.")


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.chunker = Chunker()
        self.retriever = Retriever(db)            # dense-only (kept for /search + benchmarks)
        self.advanced = AdvancedRetriever(db)     # hybrid pipeline
        self.prompts = PromptBuilder()
        self.citations = CitationEngine()

    # ---------- indexing (called by the ingestion pipeline) ----------
    def index_document(self, document_id: int, pages: list[dict]) -> int:
        chunk_dicts = self.chunker.chunk_pages(pages)
        if not chunk_dicts:
            return 0
        repo = ChunkRepository(self.db)
        rows = repo.bulk_create(document_id, chunk_dicts)

        embedder = get_embedder()
        vectors = embedder.embed([r.text for r in rows])
        chunk_ids = [r.id for r in rows]
        get_vector_store().add(chunk_ids, vectors)
        for cid in chunk_ids:
            repo.record_embedding(cid, faiss_id=str(cid),
                                  model_name=embedder.model_name,
                                  dimension=embedder.dimension)
        lexical_index.mark_dirty()   # BM25 must see the new chunks
        logger.info("Indexed document %d: %d chunks.", document_id, len(rows))
        return len(rows)

    # ---------- semantic search (dense; used by /api/search) ----------
    def semantic_search(self, query: str, top_k: int = 5) -> tuple[list, float]:
        start = time.perf_counter()
        hits = self.retriever.retrieve(query, top_k)
        latency = (time.perf_counter() - start) * 1000
        return hits, round(latency, 1)

    # ---------- streaming question answering ----------
    def answer_stream(self, question: str, prior_user_messages: list[str] | None = None):
        """Generator yielding real pipeline events (stage/token/done)."""
        start = time.perf_counter()
        trace = []

        # Trace lines use the "agent -> task [ok] Nms" grammar the UI timeline parses.
        def stage(agent: str, task: str, detail: str, ms: float):
            trace.append(f"{agent} -> {task} [ok] {ms}ms")
            return {"type": "stage", "name": agent, "detail": detail, "ms": ms}

        chunks, report = self.advanced.retrieve(question, prior_user_messages)

        planner_detail = f"query type: {report.query_type}"
        if report.expansions:
            planner_detail += f", +{len(report.expansions)} LLM rewrites"
        if report.hyde_used:
            planner_detail += ", HyDE probe"
        if report.query_used != question:
            planner_detail += ", follow-up resolved from history"
        from app.core.config import settings
        if not settings.gemini_api_key:
            planner_detail += " (LLM expansion skipped — no API key)"
        yield stage("planner", "analyze_query", planner_detail,
                    report.timings_ms.get("planner", 0))

        yield stage("retriever", "hybrid_search",
                    f"dense {report.dense_candidates} + BM25 {report.bm25_candidates} "
                    f"→ RRF fused {report.fused}",
                    report.timings_ms.get("retrieval", 0))
        yield stage("retriever", "select_context",
                    f"dedup → {report.after_dedup}, selected {report.selected}"
                    + (f", compressed −{report.compressed_chars_saved} chars"
                       if report.compressed_chars_saved else ""),
                    report.timings_ms.get("fusion_selection", 0))

        if not report.sufficient or not chunks:
            verification = {"refused": True, "faithfulness": 1.0, "uncited_claims": 0,
                            "flagged": [], "supported": 0, "cited_sentences": 0}
            yield {"type": "done", "answer": REFUSAL, "citations": [],
                   "confidence": 0.0, "quality": report.quality,
                   "verification": verification,
                   "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                   "trace": trace + ["verifier -> insufficient_evidence [ok] 0.0ms"]}
            return

        prompt = self.prompts.build(question, chunks, report.query_type)
        yield stage("answerer", "build_prompt",
                    f"adaptive prompt ({report.query_type}), {len(prompt)} chars → Gemini",
                    0)

        t = time.perf_counter()
        from app.rag.llm_client import friendly_llm_error, get_llm
        llm = get_llm()   # raises LLMNotConfiguredError -> handled by the route
        answer = ""
        try:
            for piece in llm.stream(prompt):
                token = piece.content if hasattr(piece, "content") else str(piece)
                if token:
                    answer += token
                    yield {"type": "token", "text": token}
        except Exception as exc:   # invalid key / quota -> readable message
            raise RuntimeError(friendly_llm_error(exc)) from exc
        gen_ms = round((time.perf_counter() - t) * 1000, 1)
        trace.append(f"answerer -> generation [ok] {gen_ms}ms")

        t = time.perf_counter()
        citations = self.citations.extract(answer, chunks)
        verification = verify_answer(answer, chunks)
        confidence = calibrated_confidence(report.quality, verification, len(citations))
        ver_ms = round((time.perf_counter() - t) * 1000, 1)
        yield stage("verifier", "groundedness",
                    f"faithfulness {verification['faithfulness']:.0%}, "
                    f"{verification['uncited_claims']} uncited claims", ver_ms)

        yield {"type": "done", "answer": answer, "citations": citations,
               "confidence": confidence, "quality": report.quality,
               "verification": {k: v for k, v in verification.items() if k != "flagged"},
               "latency_ms": round((time.perf_counter() - start) * 1000, 1),
               "trace": trace}

    # ---------- non-streaming answering (coordinator / reports) ----------
    def answer(self, question: str, prior_user_messages: list[str] | None = None) -> dict:
        start = time.perf_counter()
        chunks, report = self.advanced.retrieve(question, prior_user_messages)

        if not report.sufficient or not chunks:
            return {"answer": REFUSAL, "citations": [], "confidence": 0.0,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 1)}

        prompt = self.prompts.build(question, chunks, report.query_type)
        try:
            raw_answer = generate(prompt)
        except Exception as exc:
            from app.core.exceptions import ProcessingError
            from app.rag.llm_client import friendly_llm_error
            if hasattr(exc, "status_code"):   # LLMNotConfiguredError etc.
                raise
            raise ProcessingError(friendly_llm_error(exc)) from exc
        citations = self.citations.extract(raw_answer, chunks)
        verification = verify_answer(raw_answer, chunks)
        confidence = calibrated_confidence(report.quality, verification, len(citations))

        return {"answer": raw_answer, "citations": citations,
                "confidence": confidence,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
