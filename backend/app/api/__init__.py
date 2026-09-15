"""API router aggregation.

Route map (existing contract preserved, new modules additive):

    /api/auth/*          authentication & profile
    /api/documents/*     upload, list, status, preview, delete, reprocess
    /api/search          hybrid / semantic / keyword search
    /api/chat/*          multi-agent Ask AI (JSON + SSE)
    /api/conversations/* history
    /api/reports/*       summary + CSV export
    /api/analytics/*     dashboard analytics & performance
    /api/agents/*        agent registry + execution traces
    /api/evaluation/*    RAG evaluation runs & results
    /api/health          liveness (+ dependency status)
    /api/ready           readiness
    /api/metrics         prometheus-style counters
"""
from fastapi import APIRouter

from app.api import (
    agents,
    analytics,
    auth,
    chat,
    conversations,
    documents,
    evaluation,
    reports,
    search,
    system,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(reports.router)
api_router.include_router(analytics.router)
api_router.include_router(agents.router)
api_router.include_router(evaluation.router)
api_router.include_router(system.router)

__all__ = ["api_router"]
