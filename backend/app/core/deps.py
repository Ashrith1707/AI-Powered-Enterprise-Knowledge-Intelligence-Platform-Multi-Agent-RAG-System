"""FastAPI dependencies: DB session, current user, role checks, audit helper."""
from __future__ import annotations

from typing import Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.agents.base import UserInfo
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.logging_conf import user_id_var
from app.core.security import ACCESS_TOKEN, decode_token
from app.database import get_db
from app.models import AuditLog, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, ACCESS_TOKEN)
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Access token expired.", details={"reason": "expired"}) from None
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token.", details={"reason": str(exc)[:120]}) from None

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or deactivated.")
    user_id_var.set(str(user.id))
    request.state.user_id = user.id
    return user


def get_current_user_info(user: User = Depends(get_current_user)) -> UserInfo:
    return UserInfo(id=user.id, email=user.email, role=user.role.value if hasattr(user.role, "value") else str(user.role))


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise AuthorizationError("Administrator privileges required.")
    return user


def write_audit(
    db: Session,
    *,
    user_id: Optional[int],
    action: str,
    request: Optional[Request] = None,
    resource_type: str = "",
    resource_id: str = "",
    outcome: str = "success",
    detail: Optional[dict] = None,
) -> None:
    ip = ""
    ua = ""
    if request is not None:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
            request.client.host if request.client else ""
        )
        ua = request.headers.get("User-Agent", "")[:255]
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            outcome=outcome,
            ip_address=ip[:64],
            user_agent=ua,
            detail_json=detail or {},
        )
    )
    db.commit()
