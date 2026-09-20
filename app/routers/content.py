from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content_schemas import (
    AstrologerRead,
    FestivalRead,
    PlanetaryEventRead,
    RashifalRead,
    FeedbackRequest,
    SubscribeRequest,
    HeroSlideRead,
    NavItemRead,
    ServiceCardRead,
    SiteContent,
    SiteTextRead,
    ZodiacOverrideRead,
)
from app.database import get_db
from app.models import FeedbackMessage, Subscriber
from app.services import content_store

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("", response_model=SiteContent)
def get_site_content(db: Session = Depends(get_db)) -> SiteContent:
    """Everything the public site renders, in one call.

    Unpublished rows are filtered out here rather than in the browser, so a hidden
    astrologer is never sent to a visitor in the first place.
    """

    def rows(kind: str, schema):
        model = content_store.CONTENT_MODELS[kind]
        return [
            schema(**content_store.to_dict(row))
            for row in content_store.list_rows(db, model, published_only=True)
        ]

    return SiteContent(
        astrologers=rows("astrologers", AstrologerRead),
        services=rows("services", ServiceCardRead),
        hero_slides=rows("hero-slides", HeroSlideRead),
        nav_items=rows("nav-items", NavItemRead),
        texts=rows("texts", SiteTextRead),
        zodiac_overrides=rows("zodiac", ZodiacOverrideRead),
        festivals=rows("festivals", FestivalRead),
        planetary_events=rows("planetary-events", PlanetaryEventRead),
        rashifal=rows("rashifal", RashifalRead),
    )


@router.post("/subscribe", status_code=201)
def subscribe(payload: SubscribeRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Footer newsletter sign-up.

    Re-subscribing is a no-op rather than an error: telling a visitor "you are
    already subscribed" leaks who is on the list.
    """
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    existing = db.scalar(select(Subscriber).where(Subscriber.email == email))
    if existing is None:
        db.add(Subscriber(id=uuid4().hex, email=email))
        db.commit()
    return {"status": "ok"}


@router.post("/feedback", status_code=201)
def submit_feedback(payload: FeedbackRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    db.add(
        FeedbackMessage(
            id=uuid4().hex,
            message=payload.message.strip(),
            email=payload.email.strip().lower(),
        )
    )
    db.commit()
    return {"status": "ok"}
