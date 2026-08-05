"""The seven specialized agents.

Each wraps an existing service — agents are the orchestration layer,
services are the capability layer. That separation means every capability
is independently testable without the agent machinery.
"""
from sqlalchemy.orm import Session

from app.agents.base_agent import AgentResult, AgentTask, BaseAgent
from app.core.logging_config import get_logger
from app.repositories.activity_repository import ActivityRepository
from app.repositories.document_repository import DocumentRepository

logger = get_logger("agents")


class DocumentAgent(BaseAgent):
    """Runs / re-runs the ingestion pipeline and answers document lookups."""
    name = "document_agent"
    description = "Parses, OCRs and processes uploaded documents."
    capabilities = ["process_document", "get_document"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        if task.task_type == "process_document":
            from app.services.pipeline_service import PipelineService
            PipelineService(self.db).process(task.payload["document_id"])
            return self._success(task, {"document_id": task.payload["document_id"]})
        doc = DocumentRepository(self.db).get(task.payload["document_id"])
        if doc is None:
            return self._failure(task, "Document not found.")
        return self._success(task, {"id": doc.id, "filename": doc.filename,
                                    "status": doc.status, "category": doc.category})


class MetadataAgent(BaseAgent):
    """Re-extracts metadata for a document on demand."""
    name = "metadata_agent"
    description = "Extracts titles, keywords, entities and summaries."
    capabilities = ["extract_metadata"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        from app.services.metadata_service import MetadataService
        repo = DocumentRepository(self.db)
        doc = repo.get(task.payload["document_id"])
        if doc is None:
            return self._failure(task, "Document not found.")
        pages = [{"page_number": p.page_number, "text": p.text}
                 for p in repo.get_pages(doc.id)]
        meta = MetadataService().extract(doc.filename, pages)
        repo.save_metadata(doc, **meta)
        return self._success(task, meta)


class SearchAgent(BaseAgent):
    """Semantic search and RAG answering over the knowledge base."""
    name = "search_agent"
    description = "Retrieves relevant chunks and generates cited answers."
    capabilities = ["semantic_search", "rag_answer"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        from app.rag.rag_service import RAGService
        rag = RAGService(self.db)
        if task.task_type == "semantic_search":
            hits, latency = rag.semantic_search(task.payload["query"],
                                                task.payload.get("top_k", 5))
            return self._success(task, {"hits": hits, "latency_ms": latency})
        return self._success(task, rag.answer(task.payload["question"]))


class AnalyticsAgent(BaseAgent):
    """Computes platform metrics."""
    name = "analytics_agent"
    description = "Aggregates document, search and pipeline statistics."
    capabilities = ["dashboard_stats"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        from app.services.analytics_service import AnalyticsService
        return self._success(task, AnalyticsService(self.db).dashboard_stats())


class ReportAgent(BaseAgent):
    """Generates PDF/DOCX reports."""
    name = "report_agent"
    description = "Produces analytics, summary and Q&A reports."
    capabilities = ["generate_report"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        from app.services.report_service import ReportService
        report = ReportService(self.db).generate(
            title=task.payload["title"],
            report_type=task.payload.get("report_type", "analytics"),
            file_format=task.payload.get("file_format", "pdf"),
            document_ids=task.payload.get("document_ids", []),
            question=task.payload.get("question"),
        )
        return self._success(task, {"report_id": report.id,
                                    "file_path": report.file_path})


class EvaluationAgent(BaseAgent):
    """Scores a RAG answer: groundedness (citations) + non-refusal."""
    name = "evaluation_agent"
    description = "Evaluates answer quality and citation coverage."
    capabilities = ["evaluate_answer"]

    def run(self, task: AgentTask) -> AgentResult:
        answer_data = task.context.get("rag_answer") or task.payload
        answer = answer_data.get("answer", "")
        citations = answer_data.get("citations", [])
        refused = "does not contain enough information" in answer
        score = 0.0 if refused else min(1.0, 0.4 + 0.2 * len(citations))
        return self._success(task, {
            "score": round(score, 2),
            "grounded": bool(citations),
            "refused": refused,
            "citation_count": len(citations),
        })


class NotificationAgent(BaseAgent):
    """Writes user-facing events to the audit log (extensible to email/Slack)."""
    name = "notification_agent"
    description = "Records and dispatches platform notifications."
    capabilities = ["notify"]

    def __init__(self, db: Session):
        self.db = db

    def run(self, task: AgentTask) -> AgentResult:
        ActivityRepository(self.db).audit(
            actor="notification_agent", action="notify",
            entity_type=task.payload.get("entity_type", "system"),
            entity_id=task.payload.get("entity_id"),
            detail={"message": task.payload.get("message", "")})
        return self._success(task, {"delivered": True})
