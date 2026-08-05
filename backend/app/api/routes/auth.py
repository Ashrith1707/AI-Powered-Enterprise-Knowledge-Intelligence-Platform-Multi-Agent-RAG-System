"""Authentication: register, login, refresh (with rotation), logout, me."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthError, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.core.security import (create_access_token, hash_password, hash_refresh_token,
                               new_refresh_token, refresh_expiry, verify_password)
from app.models import RefreshToken, User
from app.repositories.activity_repository import ActivityRepository
from app.schemas.auth import (LoginRequest, RefreshRequest, RegisterRequest,
                              TokenResponse, UserOut)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_tokens(db: Session, user: User, remember_me: bool) -> TokenResponse:
    refresh = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_refresh_token(refresh),
                        expires_at=refresh_expiry(remember_me).replace(tzinfo=None)))
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=refresh,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise ValidationError("An account with this email already exists.")
    # First registered user becomes admin; everyone after is an analyst.
    role = "admin" if db.scalar(select(User).limit(1)) is None else "analyst"
    user = User(email=body.email.lower(), full_name=body.full_name.strip(),
                password_hash=hash_password(body.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    ActivityRepository(db).audit(user.email, "auth.register", "user", user.id)
    return _issue_tokens(db, user, remember_me=False)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        # Same message for both cases — never reveal which one failed.
        raise AuthError("Invalid email or password.")
    ActivityRepository(db).audit(user.email, "auth.login", "user", user.id)
    return _issue_tokens(db, user, body.remember_me)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken)
                    .where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if (row is None or row.revoked
            or row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)):
        raise AuthError("Refresh token invalid or expired. Sign in again.")
    # Rotation: the old token is dead the moment it is used.
    row.revoked = True
    db.commit()
    return _issue_tokens(db, row.user, remember_me=False)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken)
                    .where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if row:
        row.revoked = True
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
