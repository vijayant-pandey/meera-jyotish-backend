from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User, UserSession
from app.schemas import AuthUser, LoginRequest, SignupRequest
from app.security import generate_session_token, hash_password, hash_session_token, verify_password


def _session_expiry(settings: Settings) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.session_duration_hours)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        created_at=_as_utc(user.created_at),
    )


def register_user(db: Session, payload: SignupRequest) -> AuthUser:
    existing = db.scalar(
        select(User).where(or_(User.email == payload.email.lower(), User.phone == payload.phone))
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email or phone number is already registered.",
        )

    user = User(
        id=uuid4().hex,
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        phone=payload.phone.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_auth_user(user)


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    identifier = payload.identifier.strip()
    normalized_identifier = identifier.lower()
    user = db.scalar(
        select(User).where(or_(User.email == normalized_identifier, User.phone == identifier))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/phone or password.",
        )
    return user


def create_session_for_user(db: Session, user: User, response: Response, settings: Settings) -> AuthUser:
    token = generate_session_token()
    session = UserSession(
        id=uuid4().hex,
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=_session_expiry(settings),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="lax",
        max_age=settings.session_duration_hours * 3600,
        path="/",
    )
    return _to_auth_user(user)


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="lax",
        path="/",
    )


def logout_user(
    db: Session,
    response: Response,
    settings: Settings,
    session_token: str | None,
) -> None:
    if session_token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_session_token(session_token)))
        db.commit()
    clear_session_cookie(response, settings)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(session_token))
    )
    if session is None or _as_utc(session.expires_at) <= datetime.now(timezone.utc):
        if session is not None:
            db.delete(session)
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session.last_seen_at = datetime.now(timezone.utc)
    user = session.user
    db.add(session)
    db.commit()
    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if not request.cookies.get(settings.session_cookie_name):
        return None
    try:
        return get_current_user(request, db, settings)
    except HTTPException:
        return None


def current_user_payload(user: User) -> AuthUser:
    return _to_auth_user(user)
