"""Structured logging with request correlation.

Logs are emitted as key=value structured lines including request_id, and
sensitive values (API keys, tokens, passwords) are redacted by a filter.
"""
from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")

_REDACT_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey|token|secret|password|authorization)([\"'\s:=]+)([^\s,\"'}]{6,})"),
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{10,}"),
]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        for pat in _REDACT_PATTERNS:
            msg = pat.sub(lambda m: (m.group(1) + m.group(2) + "[REDACTED]") if m.lastindex and m.lastindex >= 2 else "[REDACTED]", msg)
        if msg != record.getMessage():
            record.msg = msg
            record.args = ()
        return True


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        rid = request_id_var.get()
        uid = user_id_var.get()
        return f"{base} request_id={rid} user_id={uid}"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        StructuredFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
    )
    handler.addFilter(RedactionFilter())
    root.handlers = [handler]
    # Quiet noisy libraries
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"knowledgeiq.{name}")


def log_agent_event(logger: logging.Logger, **fields) -> None:
    """Emit a structured agent/telemetry event."""
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("AGENT_EVENT %s", parts)
