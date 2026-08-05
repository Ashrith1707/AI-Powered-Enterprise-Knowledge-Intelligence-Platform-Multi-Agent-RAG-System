"""Application entry point. Run with:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.deps import get_current_user
from app.api.routes import (agents, analytics, auth, conversations, documents,
                            health, reports, search)
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import AppError
from app.core.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Validate the Gemini key ONCE at startup with an unmissable log line.
    from app.rag.llm_client import gemini_status
    llm = gemini_status(force=True)
    if llm["status"] == "ok":
        logger.info("GEMINI: AVAILABLE — %s", llm["detail"])
    else:
        logger.warning("GEMINI: NOT AVAILABLE (%s) — %s", llm["status"], llm["detail"])
    logger.info("%s started (env=%s).", settings.app_name, settings.app_env)
    yield


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- security headers + metrics + rate limiting ----------------
_metrics_lock = Lock()
_metrics: dict[str, dict] = defaultdict(lambda: {"count": 0, "errors": 0, "total_ms": 0.0})
_rate_buckets: dict[str, deque] = defaultdict(deque)

RATE_RULES = (  # (path prefix, requests per minute)
    ("/api/auth", settings.rate_limit_auth),
    ("/api/ask", settings.rate_limit_ask),
)


@app.middleware("http")
async def observability_and_protection(request: Request, call_next):
    path = request.url.path

    # In-memory per-IP rate limiting (swap for Redis in multi-instance setups).
    client_ip = request.client.host if request.client else "unknown"
    for prefix, per_minute in RATE_RULES:
        if path.startswith(prefix):
            bucket = _rate_buckets[f"{client_ip}:{prefix}"]
            now = time.monotonic()
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= per_minute:
                return JSONResponse(status_code=429, content={
                    "detail": "Too many requests — slow down and try again shortly."})
            bucket.append(now)
            break

    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    if path.startswith("/api"):
        key = f"{request.method} {path}"
        with _metrics_lock:
            m = _metrics[key]
            m["count"] += 1
            m["total_ms"] += elapsed_ms
            if response.status_code >= 500:
                m["errors"] += 1
        if elapsed_ms > settings.slow_request_ms:
            logger.warning("SLOW %s took %.0fms (status %d)", key, elapsed_ms,
                           response.status_code)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/api/metrics", response_class=PlainTextResponse, tags=["monitoring"])
def metrics():
    """Prometheus-compatible text exposition of per-endpoint counters."""
    lines = [
        "# HELP api_requests_total Total API requests per endpoint",
        "# TYPE api_requests_total counter",
    ]
    with _metrics_lock:
        for key, m in sorted(_metrics.items()):
            method, path = key.split(" ", 1)
            label = f'method="{method}",path="{path}"'
            lines.append(f'api_requests_total{{{label}}} {m["count"]}')
            lines.append(f'api_request_errors_total{{{label}}} {m["errors"]}')
            avg = m["total_ms"] / m["count"] if m["count"] else 0
            lines.append(f'api_request_duration_ms_avg{{{label}}} {avg:.1f}')
    return "\n".join(lines) + "\n"


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# Public: health, metrics, auth. Everything else requires a valid access token.
app.include_router(health.router)
app.include_router(auth.router)
PROTECTED = [Depends(get_current_user)]
for router in (documents.router, search.router, analytics.router,
               reports.router, agents.router, conversations.router):
    app.include_router(router, dependencies=PROTECTED)
