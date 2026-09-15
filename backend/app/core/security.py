"""Security primitives: password hashing, JWT tokens, filename sanitization.

- Passwords: bcrypt (via the `bcrypt` package directly — no legacy passlib).
- Tokens: PyJWT with a `token_type` claim so refresh tokens can never be used
  as access tokens.
- Filenames: sanitized to prevent path traversal; stored under UUID names.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.config import get_settings

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"

# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def password_strength_ok(password: str) -> bool:
    return len(password) >= 8 and re.search(r"[A-Za-z]", password) and re.search(r"\d", password)


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------

def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra: Optional[Dict[str, Any]] = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str = "user") -> str:
    settings = get_settings()
    return _create_token(
        str(user_id),
        ACCESS_TOKEN,
        timedelta(minutes=settings.access_token_expire_minutes),
        {"role": role},
    )


def create_refresh_token(user_id: int) -> str:
    settings = get_settings()
    return _create_token(str(user_id), REFRESH_TOKEN, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str) -> Dict[str, Any]:
    """Decode + validate a JWT. Raises jwt.PyJWTError subclasses on failure."""
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload


# --------------------------------------------------------------------------
# Filenames / path traversal
# --------------------------------------------------------------------------
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def sanitize_filename(raw: str) -> str:
    """Strip directories, control chars and unicode tricks from an upload name."""
    if not raw:
        return "upload"
    # Take only the basename — blocks ../../etc/passwd style traversal.
    name = PurePath(raw.replace("\\", "/")).name
    name = unicodedata.normalize("NFKD", name)
    name = _SAFE_NAME_RE.sub("_", name).strip(" ._")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "upload"
    return name[:180]


def generate_stored_name(sanitized: str) -> str:
    ext = PurePath(sanitized).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def is_within_directory(path: str, directory: str) -> bool:
    """Guard against path traversal when resolving file access."""
    try:
        resolved = (PurePath(path)).__class__(path)  # keep type
        from pathlib import Path

        return Path(path).resolve().is_relative_to(Path(directory).resolve())
    except (OSError, ValueError):
        return False
