"""HTTP middleware: request IDs, security headers, rate limiting, metrics."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Callable, Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.logging_conf import request_id_var

# ---------------------------------------------------------------------------
# In-process metrics counters (exposed at /api/metrics)
# ---------------------------------------------------------------------------
_metrics_lock = Lock()
_metrics: Dict[str, float] = defaultdict(float)
_latency_samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=500))


def record_metric(name: str, value: float = 1.0) -> None:
    with _metrics_lock:
        _metrics[name] += value


def record_latency(name: str, seconds: float) -> None:
    with _metrics_lock:
        _latency_samples[name].append(seconds)
        _metrics[f"{name}_count"] += 1
        _metrics[f"{name}_sum_seconds"] += seconds


def snapshot_metrics() -> Dict[str, object]:
    with _metrics_lock:
        out: Dict[str, object] = dict(_metrics)
        for name, samples in _latency_samples.items():
            if samples:
                ordered = sorted(samples)
                out[f"{name}_p50_ms"] = round(ordered[len(ordered) // 2] * 1000, 1)
                out[f"{name}_p95_ms"] = round(ordered[int(len(ordered) * 0.95) - 1 if len(ordered) > 1 else 0] * 1000, 1)
        return out


# ---------------------------------------------------------------------------
# Request ID + latency middleware
# ---------------------------------------------------------------------------
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        elapsed = time.perf_counter() - started
        response.headers["X-Request-ID"] = rid
        record_latency("http_request", elapsed)
        record_metric(f"http_status_{response.status_code}")
        return response


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if get_settings().is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


# ---------------------------------------------------------------------------
# Sliding-window rate limiting (per client IP; stricter on auth endpoints)
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=1000))
        self._lock = Lock()

    def allow(self, key: str, bucket: str, limit_per_minute: int) -> Tuple[bool, int]:
        now = time.time()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit_per_minute:
                retry_after = int(60 - (now - q[0])) + 1
                return False, retry_after
            q.append(now)
            return True, 0


_rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        path = request.url.path
        if not path.startswith("/api") or path.startswith("/api/health") or path.startswith("/api/ready"):
            return await call_next(request)

        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        bucket = "auth" if path.startswith("/api/auth") else "api"
        limit = settings.rate_limit_auth_per_minute if bucket == "auth" else settings.rate_limit_per_minute
        allowed, retry_after = _rate_limiter.allow(client_ip, bucket, limit)
        if not allowed:
            record_metric("rate_limited")
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down."}},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


def reset_rate_limiter_for_tests() -> None:
    with _rate_limiter._lock:
        _rate_limiter._hits.clear()
