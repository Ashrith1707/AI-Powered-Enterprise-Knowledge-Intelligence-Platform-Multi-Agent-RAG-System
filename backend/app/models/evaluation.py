from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationResult(Base):
    """A single evaluation run of the RAG pipeline (Module 7).

    Metrics are computed by actually running the pipeline against a labeled
    golden dataset — scores are never fabricated. When an LLM judge is
    unavailable, LLM-based metrics are recorded as `null` with a reason.
    """

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(120), default="golden")
    num_queries: Mapped[int] = mapped_column(Integer, default=0)
    provider_mode: Mapped[str] = mapped_column(String(40), default="")  # gemini | mock | local

    retrieval_metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    generation_metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    system_metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    per_query_json: Mapped[list] = mapped_column(JSON, default=list)

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
