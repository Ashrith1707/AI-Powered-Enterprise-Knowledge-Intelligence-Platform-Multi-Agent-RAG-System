"""Shared FastAPI dependencies: the authenticated-user guard."""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class AuthError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


def get_current_user(token: str | None = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    if not token:
        raise AuthError("Not authenticated. Sign in to continue.")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthError("Session expired or token invalid. Sign in again.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthError("Account no longer exists.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ForbiddenError("This action requires the admin role.")
    return user
