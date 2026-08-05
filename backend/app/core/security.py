"""Password hashing (bcrypt) and JWT creation/verification (PyJWT, HS256).

Refresh tokens are opaque random strings stored HASHED in the database
(sha256), rotated on every use and revocable — the JWT is only ever the
short-lived access token.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("security")
ALGORITHM = "HS256"

if settings.app_env == "production" and "change-me" in settings.secret_key:
    logger.error("SECRET_KEY is still the dev default in production — set SECRET_KEY!")


# ---------- passwords ----------
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------- access tokens (JWT) ----------
def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns the payload or None for anything invalid/expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload if payload.get("type") == "access" else None
    except jwt.PyJWTError:
        return None


# ---------- refresh tokens (opaque, stored hashed) ----------
def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expiry(remember_me: bool) -> datetime:
    days = settings.refresh_token_days_remember if remember_me else settings.refresh_token_days
    return datetime.now(timezone.utc) + timedelta(days=days)
