from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_session_for_user,
    current_user_payload,
    get_current_user,
    logout_user,
    register_user,
)
from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.schemas import AuthUser, LoginRequest, SignupRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthUser)
async def register(
    payload: SignupRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    auth_user = register_user(db, payload)
    user = db.get(User, auth_user.id)
    assert user is not None
    return create_session_for_user(db, user, response, settings)


@router.post("/login", response_model=AuthUser)
async def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    user = authenticate_user(db, payload)
    return create_session_for_user(db, user, response, settings)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    logout_user(db, response, settings, request.cookies.get(settings.session_cookie_name))
    return {"status": "ok"}


@router.get("/me", response_model=AuthUser)
async def me(user: User = Depends(get_current_user)) -> AuthUser:
    return current_user_payload(user)
