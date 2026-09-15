"""Evaluation API — trigger runs, list results, inspect a run."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.errors import NotFoundError
from app.database import get_db
from app.models import EvaluationResult, User

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _result_out(row: EvaluationResult, include_per_query: bool = False) -> dict:
    out = {
        "id": row.id,
        "run_id": row.run_id,
        "dataset_name": row.dataset_name,
        "num_queries": row.num_queries,
        "provider_mode": row.provider_mode,
        "overall_score": row.overall_score,
        "retrieval_metrics": row.retrieval_metrics_json or {},
        "generation_metrics": row.generation_metrics_json or {},
        "system_metrics": row.system_metrics_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_per_query:
        out["per_query"] = row.per_query_json or []
    return out


@router.post("/run", status_code=202)
def trigger_run(background_tasks: BackgroundTasks, user: User = Depends(require_admin)):
    """Kick off the golden-dataset evaluation in the background (admin only).

    The run executes the real pipeline end-to-end; poll GET /api/evaluation/results
    for the new run when it completes.
    """
    import asyncio

    from app.evaluation.run import run_evaluation

    def _job() -> None:
        try:
            asyncio.run(run_evaluation())
        except Exception:  # noqa: BLE001 — logged inside run_evaluation
            from app.core.logging_conf import get_logger

            get_logger("evaluation").exception("Evaluation run failed")

    background_tasks.add_task(_job)
    return {"status": "started", "message": "Evaluation run started in the background."}


@router.get("/results")
def list_results(db: Session = Depends(get_db), user: User = Depends(get_current_user), limit: int = 20):
    rows = db.execute(
        select(EvaluationResult).order_by(EvaluationResult.created_at.desc()).limit(max(1, min(limit, 100)))
    ).scalars().all()
    return {"items": [_result_out(r) for r in rows]}


@router.get("/results/{run_id}")
def get_result(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.execute(select(EvaluationResult).where(EvaluationResult.run_id == run_id)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Evaluation run '{run_id}' not found.")
    return _result_out(row, include_per_query=True)
