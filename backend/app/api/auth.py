"""Authentication routes: register, login, refresh, me, logout, profile update."""
from __future__ import annotations

from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, write_audit
from app.core.errors import AuthenticationError, InputValidationError
from app.core.security import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_strength_ok,
    verify_password,
)
from app.database import get_db
from app.models import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenResponse:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return TokenResponse(
        access_token=create_access_token(user.id, role),
        refresh_token=create_refresh_token(user.id),
        expires_in_minutes=get_settings().access_token_expire_minutes,
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        write_audit(db, user_id=existing.id, action="register", request=request, outcome="failure",
                    detail={"reason": "duplicate_email"})
        raise InputValidationError("An account with this email already exists.")
    if not password_strength_ok(payload.password):
        raise InputValidationError(
            "Password must be at least 8 characters and include letters and numbers."
        )

    # First registered user becomes admin (bootstrap); others are regular users.
    is_first = db.execute(select(User.id).limit(1)).first() is None
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.admin if is_first else UserRole.user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    write_audit(db, user_id=user.id, action="register", request=request,
                detail={"role": user.role.value})
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        write_audit(db, user_id=user.id if user else None, action="login", request=request,
                    outcome="failure", detail={"reason": "invalid_credentials"})
        # Safe error message: do not reveal whether the email exists.
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    write_audit(db, user_id=user.id, action="login", request=request)
    return _tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token, REFRESH_TOKEN)
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid or expired refresh token.") from None
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or deactivated.")
    return _tokens(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: UserUpdate, request: Request, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()[:160]
    if payload.password:
        if not password_strength_ok(payload.password):
            raise InputValidationError(
                "Password must be at least 8 characters and include letters and numbers."
            )
        user.hashed_password = hash_password(payload.password)
        write_audit(db, user_id=user.id, action="password_change", request=request)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Stateless JWT: logout is an audit event; clients discard tokens.
    write_audit(db, user_id=user.id, action="logout", request=request)
    return None
