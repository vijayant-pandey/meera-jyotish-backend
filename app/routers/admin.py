from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.admin_auth import (
    ADMIN_COOKIE_NAME,
    authenticate_admin,
    end_admin_session,
    require_admin,
    start_admin_session,
)
from app.config import Settings, get_settings
from app.content_schemas import (
    AdminLoginRequest,
    AdminUserRead,
    AstrologerRead,
    AstrologerWrite,
    HeroSlideRead,
    HeroSlideWrite,
    MediaUploadResult,
    NavItemRead,
    NavItemWrite,
    ServiceCardRead,
    ServiceCardWrite,
    FeedbackRead,
    FeedbackRequest,
    FestivalRead,
    FestivalWrite,
    PlanetaryEventRead,
    PlanetaryEventWrite,
    RashifalRead,
    RashifalWrite,
    SiteTextRead,
    SiteTextWrite,
    SubscriberRead,
    SubscribeRequest,
    ZodiacOverrideRead,
    ZodiacOverrideWrite,
)
from app.database import get_db
from app.models import AdminUser
from app.services import content_store

router = APIRouter(prefix="/api/admin", tags=["admin"])

# kind -> (model, write schema, read schema)
CONTENT_REGISTRY: dict[str, tuple[type[Any], type[Any], type[Any]]] = {
    "astrologers": (content_store.CONTENT_MODELS["astrologers"], AstrologerWrite, AstrologerRead),
    "services": (content_store.CONTENT_MODELS["services"], ServiceCardWrite, ServiceCardRead),
    "hero-slides": (content_store.CONTENT_MODELS["hero-slides"], HeroSlideWrite, HeroSlideRead),
    "nav-items": (content_store.CONTENT_MODELS["nav-items"], NavItemWrite, NavItemRead),
    "texts": (content_store.CONTENT_MODELS["texts"], SiteTextWrite, SiteTextRead),
    "zodiac": (content_store.CONTENT_MODELS["zodiac"], ZodiacOverrideWrite, ZodiacOverrideRead),
    # Collected from visitors, so the admin panel lists and deletes but does not author them.
    "subscribers": (content_store.CONTENT_MODELS["subscribers"], SubscribeRequest, SubscriberRead),
    "feedback": (content_store.CONTENT_MODELS["feedback"], FeedbackRequest, FeedbackRead),
    "festivals": (content_store.CONTENT_MODELS["festivals"], FestivalWrite, FestivalRead),
    "planetary-events": (content_store.CONTENT_MODELS["planetary-events"], PlanetaryEventWrite, PlanetaryEventRead),
    "rashifal": (content_store.CONTENT_MODELS["rashifal"], RashifalWrite, RashifalRead),
}

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "media"
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
MAX_UPLOAD_BYTES = 3 * 1024 * 1024


def _registry(kind: str) -> tuple[type[Any], type[Any], type[Any]]:
    entry = CONTENT_REGISTRY.get(kind)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown content type '{kind}'.")
    return entry


# --- authentication ----------------------------------------------------------


@router.post("/login", response_model=AdminUserRead)
def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserRead:
    admin = authenticate_admin(db, payload.username, payload.password)
    start_admin_session(db, admin, response, settings)
    return AdminUserRead(
        id=admin.id, username=admin.username, name=admin.name, last_login_at=admin.last_login_at
    )


@router.post("/logout")
def admin_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    end_admin_session(db, response, settings, request.cookies.get(ADMIN_COOKIE_NAME))
    return {"status": "ok"}


@router.get("/me", response_model=AdminUserRead)
def admin_me(admin: AdminUser = Depends(require_admin)) -> AdminUserRead:
    return AdminUserRead(
        id=admin.id, username=admin.username, name=admin.name, last_login_at=admin.last_login_at
    )


# --- content CRUD ------------------------------------------------------------


@router.get("/content/{kind}")
def list_content(
    kind: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[dict[str, Any]]:
    model, _write, read_schema = _registry(kind)
    rows = content_store.list_rows(db, model)
    return [read_schema(**content_store.to_dict(row)).model_dump(by_alias=True) for row in rows]


@router.post("/content/{kind}", status_code=status.HTTP_201_CREATED)
def create_content(
    kind: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict[str, Any]:
    model, write_schema, read_schema = _registry(kind)
    validated = write_schema.model_validate(payload)
    row = content_store.create_row(db, model, validated.model_dump())
    return read_schema(**content_store.to_dict(row)).model_dump(by_alias=True)


@router.put("/content/{kind}/{row_id}")
def update_content(
    kind: str,
    row_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict[str, Any]:
    model, write_schema, read_schema = _registry(kind)
    row = content_store.get_row(db, model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    validated = write_schema.model_validate(payload)
    row = content_store.update_row(db, row, validated.model_dump())
    return read_schema(**content_store.to_dict(row)).model_dump(by_alias=True)


@router.delete("/content/{kind}/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(
    kind: str,
    row_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Response:
    model, _write, _read = _registry(kind)
    row = content_store.get_row(db, model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    content_store.delete_row(db, row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/content/{kind}/reorder")
def reorder_content(
    kind: str,
    payload: dict[str, list[str]],
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict[str, str]:
    model, _write, _read = _registry(kind)
    content_store.reorder(db, model, payload.get("ids", []))
    return {"status": "ok"}


# --- media -------------------------------------------------------------------


@router.post("/media", response_model=MediaUploadResult)
async def upload_media(
    file: UploadFile = File(...),
    _: AdminUser = Depends(require_admin),
) -> MediaUploadResult:
    extension = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}.",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # The stored name is generated, never taken from the upload, so a crafted
    # filename cannot traverse out of the media directory or overwrite anything.
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"{secrets.token_hex(16)}{extension}"
    (MEDIA_ROOT / stored_name).write_bytes(data)

    return MediaUploadResult(
        url=f"/media/{stored_name}",
        filename=stored_name,
        content_type=file.content_type or "application/octet-stream",
        bytes=len(data),
    )
