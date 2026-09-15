"""System routes: health, readiness, Prometheus-style metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.middleware import snapshot_metrics
from app.database import get_db
from app.services.embeddings import embedding_provider_status
from app.services.llm import get_llm_provider
from app.services.ocr import get_ocr_capability
from app.services.vector_store import FAISS_AVAILABLE, vector_store_status

router = APIRouter(tags=["system"])


def _db_ok(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness + dependency status. Honest provider reporting (mock vs gemini)."""
    settings = get_settings()
    llm = get_llm_provider()
    ocr = get_ocr_capability()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "database": "ok" if _db_ok(db) else "error",
        "vector_store": vector_store_status(),
        "faiss_available": FAISS_AVAILABLE,
        "llm": {"provider": llm.name, "model": getattr(llm, "model", "mock-extractive-v1")},
        "embeddings": embedding_provider_status(),
        "ocr": {"tesseract": ocr.tesseract_available, "pdf_rendering": ocr.pdf_rendering_available},
        "config_problems": settings.validate_environment(),
    }


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe: DB reachable and vector store loadable."""
    db_ok = _db_ok(db)
    try:
        vector_store_status()
        vector_ok = True
    except Exception:  # noqa: BLE001
        vector_ok = False
    ok = db_ok and vector_ok
    return {
        "status": "ready" if ok else "not_ready",
        "database": "ok" if db_ok else "error",
        "vector_store": "ok" if vector_ok else "error",
    } if ok else _not_ready(db_ok, vector_ok)


def _not_ready(db_ok: bool, vector_ok: bool):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "database": "ok" if db_ok else "error",
            "vector_store": "ok" if vector_ok else "error",
        },
    )


@router.get("/metrics")
def metrics():
    """Prometheus-style text metrics from in-process counters."""
    snapshot = snapshot_metrics()
    lines = ["# KnowledgeIQ metrics"]
    for key in sorted(snapshot):
        value = snapshot[key]
        if isinstance(value, (int, float)):
            metric_name = f"knowledgeiq_{key.replace('.', '_')}"
            lines.append(f"{metric_name} {value}")
    return {"metrics": "\n".join(lines), "raw": snapshot}
