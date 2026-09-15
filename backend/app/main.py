"""KnowledgeIQ FastAPI application.

Run (development):
    uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
Docs:
    http://127.0.0.1:8001/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging_conf import configure_logging, get_logger
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.database import init_db

logger = get_logger("main")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        # Warm the retrieval indexes so first query is fast.
        try:
            from app.database import get_session_factory
            from app.rag.bm25 import ensure_bm25_loaded
            from app.services.vector_store import get_vector_store

            session = get_session_factory()()
            try:
                ensure_bm25_loaded(session)
            finally:
                session.close()
            store = get_vector_store()
            logger.info("Startup complete: vectors=%d bm25 ready", store.count)
        except Exception:  # noqa: BLE001 — never block startup on warm-up
            logger.exception("Index warm-up failed (will retry lazily).")

        for problem in settings.validate_environment():
            logger.warning("CONFIG: %s", problem)
        yield

    app = FastAPI(
        title=f"{settings.app_name} API",
        description="Enterprise Knowledge Intelligence Platform — Multi-Agent RAG System",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root():  # pragma: no cover
        return {"app": settings.app_name, "status": "ok", "docs": "/docs"}

    return app


app = create_app()
