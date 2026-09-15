"""Structured errors + AI provider error classification.

CRITICAL: The platform must distinguish *why* an AI call failed. A 404 from
Gemini means "model unavailable" — NOT "API key invalid". Every AI error is
classified into a stable machine-readable code that the frontend displays.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------
class KnowledgeIQError(Exception):
    """Base class for all structured application errors."""

    code: str = "internal_error"
    http_status: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(KnowledgeIQError):
    code = "authentication_failed"
    http_status = 401
    default_message = "Invalid credentials or expired token."


class AuthorizationError(KnowledgeIQError):
    code = "permission_denied"
    http_status = 403
    default_message = "You do not have access to this resource."


class NotFoundError(KnowledgeIQError):
    code = "not_found"
    http_status = 404
    default_message = "Resource not found."


class InputValidationError(KnowledgeIQError):
    code = "validation_error"
    http_status = 422
    default_message = "Invalid input."


class RateLimitError(KnowledgeIQError):
    code = "rate_limited"
    http_status = 429
    default_message = "Too many requests. Please slow down."


class UploadError(KnowledgeIQError):
    code = "upload_rejected"
    http_status = 400
    default_message = "File upload was rejected."


class DocumentProcessingError(KnowledgeIQError):
    code = "document_processing_failed"
    http_status = 500
    default_message = "Document processing failed."


class InsufficientEvidenceError(KnowledgeIQError):
    code = "insufficient_evidence"
    http_status = 200  # surfaced inside chat payloads, not as HTTP failure
    default_message = "The available documents do not contain enough information to answer."


# ---------------------------------------------------------------------------
# AI provider error classification
# ---------------------------------------------------------------------------
class AIErrorCode(str, Enum):
    INVALID_API_KEY = "invalid_api_key"            # 401
    PERMISSION_DENIED = "permission_denied"        # 403
    MODEL_NOT_FOUND = "model_not_found"            # 404
    QUOTA_EXCEEDED = "quota_exceeded"              # 429
    INVALID_REQUEST = "invalid_request"            # 400
    PROVIDER_ERROR = "provider_error"              # 5xx
    NETWORK_ERROR = "network_error"                # connection failures
    TIMEOUT = "timeout"                            # deadlines exceeded
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNKNOWN = "unknown_ai_error"


_USER_FACING = {
    AIErrorCode.INVALID_API_KEY: "Gemini authentication failed (401). The API key is invalid or revoked.",
    AIErrorCode.PERMISSION_DENIED: "Gemini access denied (403). The key lacks permission for this API/model.",
    AIErrorCode.MODEL_NOT_FOUND: (
        "The configured model is not available (404). Check GEMINI_MODEL / "
        "GEMINI_EMBEDDING_MODEL — e.g. text-embedding-004 is deprecated; use gemini-embedding-001."
    ),
    AIErrorCode.QUOTA_EXCEEDED: "Gemini quota/rate limit reached (429). Retry later or check billing.",
    AIErrorCode.INVALID_REQUEST: "Gemini rejected the request (400).",
    AIErrorCode.PROVIDER_ERROR: "Gemini provider error (5xx). The service is temporarily unavailable.",
    AIErrorCode.NETWORK_ERROR: "Could not reach Gemini — network/connection error.",
    AIErrorCode.TIMEOUT: "Gemini request timed out.",
    AIErrorCode.UNSUPPORTED_OPERATION: "This operation is not supported by the configured model.",
    AIErrorCode.UNKNOWN: "AI provider returned an unrecognized error.",
}


class AIProviderError(KnowledgeIQError):
    """An error from the AI layer, carrying a classified :class:`AIErrorCode`."""

    code = "ai_provider_error"
    http_status = 502

    def __init__(
        self,
        error_code: AIErrorCode,
        raw_message: str = "",
        model: Optional[str] = None,
        retryable: bool = False,
    ):
        self.error_code = error_code
        self.raw_message = _redact_secrets(raw_message)[:500]
        self.model = model
        self.retryable = retryable
        self.message = _USER_FACING.get(error_code, _USER_FACING[AIErrorCode.UNKNOWN])
        details = {
            "ai_error_code": error_code.value,
            "user_message": self.message,
            "retryable": retryable,
        }
        if model:
            details["model"] = model
        if self.raw_message:
            details["provider_message"] = self.raw_message
        super().__init__(self.message, details)


def _redact_secrets(text: str) -> str:
    """Never leak API keys/tokens through error messages or logs."""
    text = re.sub(r"(?i)(api[_-]?key|token|secret|authorization)[\"'\s:=]+[A-Za-z0-9_\-\.]{8,}", r"\1=[REDACTED]", text)
    text = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "[REDACTED_KEY]", text)
    return text


def classify_ai_error(exc: Exception, model: Optional[str] = None) -> AIProviderError:
    """Map any exception raised by the AI layer to a classified AIProviderError.

    Handles the new ``google-genai`` SDK error hierarchy, HTTP errors, network
    errors and timeouts — differentiating 401 / 403 / 404 / 429 / 5xx /
    network / timeout instead of blanket "API key is invalid" messages.
    """
    if isinstance(exc, AIProviderError):
        return exc

    text = _redact_secrets(str(exc))
    lowered = text.lower()
    status = _extract_status_code(exc)

    # --- Timeouts / network (check before status codes) ---
    if isinstance(exc, TimeoutError) or "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
        return AIProviderError(AIErrorCode.TIMEOUT, text, model, retryable=True)
    if (
        "connection" in lowered and ("refused" in lowered or "reset" in lowered or "error" in lowered or "failed" in lowered)
    ) or "unreachable" in lowered or "name or service not known" in lowered or "getaddrinfo" in lowered:
        return AIProviderError(AIErrorCode.NETWORK_ERROR, text, model, retryable=True)

    # --- HTTP status based ---
    if status is not None:
        if status in (400,):
            return AIProviderError(AIErrorCode.INVALID_REQUEST, text, model)
        if status == 401 or ("invalid api key" in lowered or "api key not valid" in lowered):
            return AIProviderError(AIErrorCode.INVALID_API_KEY, text, model)
        if status == 403 or "permission" in lowered and "denied" in lowered:
            return AIProviderError(AIErrorCode.PERMISSION_DENIED, text, model)
        if status == 404 or "is not found for api version" in lowered or "not found" in lowered and "model" in lowered:
            return AIProviderError(AIErrorCode.MODEL_NOT_FOUND, text, model)
        if status == 429 or "quota" in lowered or "rate limit" in lowered or "resource exhausted" in lowered:
            return AIProviderError(AIErrorCode.QUOTA_EXCEEDED, text, model, retryable=True)
        if 500 <= status < 600:
            return AIProviderError(AIErrorCode.PROVIDER_ERROR, text, model, retryable=True)

    # --- Message-based fallbacks ---
    if "unsupported" in lowered:
        return AIProviderError(AIErrorCode.UNSUPPORTED_OPERATION, text, model)
    if "invalid api key" in lowered or "api key not valid" in lowered or "unauthenticated" in lowered:
        return AIProviderError(AIErrorCode.INVALID_API_KEY, text, model)
    if "model" in lowered and ("not found" in lowered or "does not exist" in lowered):
        return AIProviderError(AIErrorCode.MODEL_NOT_FOUND, text, model)

    return AIProviderError(AIErrorCode.UNKNOWN, text, model)


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Best-effort extraction of an HTTP status code from provider SDK errors."""
    for attr in ("code", "status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int) and 100 <= val < 600:
            return val
    # google.genai errors render like: "404 models/text-embedding-004 is not found..."
    m = re.match(r"^\s*(\d{3})\b", str(exc))
    if m:
        return int(m.group(1))
    m = re.search(r"\bstatus[:\s=]+(\d{3})\b", str(exc), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------
def _error_response(status: int, code: str, message: str, details: Optional[Dict[str, Any]] = None,
                    request_id: Optional[str] = None) -> JSONResponse:
    body: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=status, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KnowledgeIQError)
    async def _handle_domain_error(request: Request, exc: KnowledgeIQError):
        return _error_response(
            exc.http_status,
            exc.code,
            exc.message,
            exc.details or None,
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        return _error_response(
            exc.status_code,
            f"http_{exc.status_code}",
            str(exc.detail),
            None,
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        # Safe error messages: never leak internals to clients.
        from app.core.logging_conf import get_logger

        get_logger("errors").exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(
            500,
            "internal_error",
            "An internal server error occurred.",
            None,
            getattr(request.state, "request_id", None),
        )
