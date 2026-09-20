from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import AdminSession, AdminUser
from app.security import generate_session_token, hash_password, hash_session_token, verify_password

# Deliberately distinct from the public session cookie. A visitor's session token
# must never be usable against an admin endpoint, and vice versa.
ADMIN_COOKIE_NAME = "kundali_admin_session"
ADMIN_SESSION_HOURS = 12


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_admin_user(db: Session, username: str, name: str, password: str) -> AdminUser:
    normalized = username.strip().lower()
    if db.scalar(select(AdminUser).where(AdminUser.username == normalized)) is not None:
        raise ValueError(f"Admin '{normalized}' already exists.")
    if len(password) < 8:
        raise ValueError("Admin password must be at least 8 characters.")
    admin = AdminUser(
        id=uuid4().hex,
        username=normalized,
        name=name.strip() or normalized,
        password_hash=hash_password(password),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def authenticate_admin(db: Session, username: str, password: str) -> AdminUser:
    admin = db.scalar(select(AdminUser).where(AdminUser.username == username.strip().lower()))
    # Always run a hash comparison, even when the account does not exist, so the
    # response time cannot be used to enumerate valid admin usernames.
    reference = admin.password_hash if admin else hash_password("invalid-placeholder")
    password_ok = verify_password(password, reference)
    if admin is None or not admin.is_active or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin username or password.",
        )
    admin.last_login_at = datetime.now(timezone.utc)
    db.add(admin)
    db.commit()
    return admin


def start_admin_session(db: Session, admin: AdminUser, response: Response, settings: Settings) -> None:
    token = generate_session_token()
    db.add(
        AdminSession(
            id=uuid4().hex,
            admin_id=admin.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ADMIN_SESSION_HOURS),
        )
    )
    db.commit()
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.session_secure_cookie,
        # Stricter than the public cookie: an admin session should never ride along
        # with a cross-site request.
        samesite="strict",
        max_age=ADMIN_SESSION_HOURS * 3600,
        path="/",
    )


def end_admin_session(db: Session, response: Response, settings: Settings, token: str | None) -> None:
    if token:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == hash_session_token(token)))
        db.commit()
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="strict",
        path="/",
    )


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUser:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin sign-in required.")

    session = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == hash_session_token(token))
    )
    if session is None or _as_utc(session.expires_at) <= datetime.now(timezone.utc):
        if session is not None:
            db.delete(session)
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin sign-in required.")

    admin = session.admin
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account is disabled.")
    return admin
