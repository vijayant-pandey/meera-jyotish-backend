from __future__ import annotations

from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Astrologer,
    FeedbackMessage,
    Festival,
    HeroSlide,
    NavItem,
    PlanetaryEvent,
    Rashifal,
    ServiceCard,
    SiteText,
    Subscriber,
    ZodiacOverride,
)

ModelT = TypeVar("ModelT")

# Columns stored as comma-separated text but exposed to the API as a list. Keeping
# the split here means neither the router nor the admin UI has to know about it.
LIST_FIELDS = {"languages", "skills"}


def _split(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _join(values: list[str]) -> str:
    return ", ".join(part.strip() for part in values if part and part.strip())


def to_dict(row: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        data[column.name] = _split(value) if column.name in LIST_FIELDS else value
    return data


def apply_payload(row: Any, payload: dict[str, Any]) -> Any:
    for key, value in payload.items():
        if not hasattr(row, key) or key in {"id", "created_at", "updated_at"}:
            continue
        setattr(row, key, _join(value) if key in LIST_FIELDS else value)
    return row


def list_rows(db: Session, model: type[ModelT], *, published_only: bool = False) -> list[ModelT]:
    statement = select(model)
    if published_only:
        statement = statement.where(model.published.is_(True))  # type: ignore[attr-defined]
    statement = statement.order_by(model.position, model.created_at)  # type: ignore[attr-defined]
    return list(db.scalars(statement))


def get_row(db: Session, model: type[ModelT], row_id: str) -> ModelT | None:
    return db.get(model, row_id)


def create_row(db: Session, model: type[ModelT], payload: dict[str, Any]) -> ModelT:
    row = model(id=uuid4().hex)  # type: ignore[call-arg]
    apply_payload(row, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_row(db: Session, row: Any, payload: dict[str, Any]) -> Any:
    apply_payload(row, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_row(db: Session, row: Any) -> None:
    db.delete(row)
    db.commit()


def reorder(db: Session, model: type[ModelT], ordered_ids: list[str]) -> None:
    """Persist a drag-to-reorder from the admin panel."""
    for index, row_id in enumerate(ordered_ids):
        row = db.get(model, row_id)
        if row is not None:
            row.position = index  # type: ignore[attr-defined]
            db.add(row)
    db.commit()


CONTENT_MODELS: dict[str, type[Any]] = {
    "astrologers": Astrologer,
    "services": ServiceCard,
    "hero-slides": HeroSlide,
    "nav-items": NavItem,
    "texts": SiteText,
    "zodiac": ZodiacOverride,
    "subscribers": Subscriber,
    "feedback": FeedbackMessage,
    "festivals": Festival,
    "planetary-events": PlanetaryEvent,
    "rashifal": Rashifal,
}
