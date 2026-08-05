from fastapi import APIRouter

from app.core.config import settings
from app.rag.llm_client import gemini_status

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    llm = gemini_status()   # cached; validates the key, not just its presence
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env,
            "llm_configured": llm["status"] == "ok",
            "llm_status": llm["status"],
            "llm_detail": llm["detail"],
            "llm_model": llm["model"]}
