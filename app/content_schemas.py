from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas import CamelModel


class AdminLoginRequest(CamelModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class AdminUserRead(CamelModel):
    id: str
    username: str
    name: str
    last_login_at: datetime | None = None


class ContentBase(CamelModel):
    position: int = 0
    published: bool = True


class ContentRead(ContentBase):
    id: str
    updated_at: datetime


# --- astrologers -------------------------------------------------------------

class AstrologerWrite(ContentBase):
    name: str = Field(min_length=1, max_length=120)
    avatar_url: str = Field(default="", max_length=500)
    languages: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    rating: float = Field(default=5.0, ge=0, le=5)
    experience_years: int = Field(default=0, ge=0, le=100)
    orders: int = Field(default=0, ge=0)
    price_per_minute: int = Field(default=0, ge=0)
    is_free: bool = True
    chat_enabled: bool = True
    call_enabled: bool = True
    trending: bool = False
    online: bool = True


class AstrologerRead(AstrologerWrite, ContentRead):
    pass


# --- service cards -----------------------------------------------------------

class ServiceCardWrite(ContentBase):
    title: str = Field(min_length=1, max_length=160)
    text: str = ""
    image_url: str = Field(default="", max_length=500)
    action_label: str = Field(default="Coming Soon", max_length=80)
    target_route: str = Field(default="", max_length=200)


class ServiceCardRead(ServiceCardWrite, ContentRead):
    pass


# --- hero slides -------------------------------------------------------------

class HeroSlideWrite(ContentBase):
    title: str = Field(min_length=1, max_length=160)
    text: str = ""
    image_url: str = Field(default="", max_length=500)


class HeroSlideRead(HeroSlideWrite, ContentRead):
    pass


# --- nav items ---------------------------------------------------------------

class NavItemWrite(ContentBase):
    label: str = Field(min_length=1, max_length=120)
    page: str = Field(default="coming-soon", max_length=60)
    coming_soon_title: str = Field(default="", max_length=160)
    requires_auth: bool = False
    # Blank for a top-level item; otherwise the label of its parent.
    parent_label: str = Field(default="", max_length=120)


class NavItemRead(NavItemWrite, ContentRead):
    pass


# --- free-form page copy -----------------------------------------------------

class SiteTextWrite(ContentBase):
    key: str = Field(min_length=1, max_length=160)
    label: str = Field(default="", max_length=200)
    value: str = ""


class SiteTextRead(SiteTextWrite, ContentRead):
    pass


# --- zodiac copy overrides ---------------------------------------------------

class ZodiacOverrideWrite(ContentBase):
    slug: str = Field(min_length=1, max_length=40)
    tagline: str = ""
    personality: str = ""
    career: str = ""
    relationships: str = ""
    health: str = ""
    finance: str = ""


class ZodiacOverrideRead(ZodiacOverrideWrite, ContentRead):
    pass


class FestivalWrite(ContentBase):
    name: str = Field(min_length=1, max_length=200)
    occurs_on: str = Field(default="", max_length=10)
    image_url: str = Field(default="", max_length=500)
    note: str = ""


class FestivalRead(FestivalWrite, ContentRead):
    pass


class PlanetaryEventWrite(ContentBase):
    title: str = Field(min_length=1, max_length=240)
    occurs_at: str = Field(default="", max_length=25)
    note: str = ""


class PlanetaryEventRead(PlanetaryEventWrite, ContentRead):
    pass


class RashifalWrite(ContentBase):
    sign: str = Field(min_length=1, max_length=40)
    text: str = ""
    image_url: str = Field(default="", max_length=500)


class RashifalRead(RashifalWrite, ContentRead):
    pass


class SubscribeRequest(CamelModel):
    email: str = Field(min_length=5, max_length=255)


class FeedbackRequest(CamelModel):
    message: str = Field(min_length=3, max_length=4000)
    email: str = Field(default="", max_length=255)


class SubscriberRead(ContentRead):
    email: str


class FeedbackRead(ContentRead):
    message: str
    email: str = ""


class MediaUploadResult(CamelModel):
    url: str
    filename: str
    content_type: str
    bytes: int


class SiteContent(CamelModel):
    """Everything the public site needs, in one request."""

    astrologers: list[AstrologerRead]
    services: list[ServiceCardRead]
    hero_slides: list[HeroSlideRead]
    nav_items: list[NavItemRead]
    texts: list[SiteTextRead]
    zodiac_overrides: list[ZodiacOverrideRead]
    festivals: list[FestivalRead]
    planetary_events: list[PlanetaryEventRead]
    rashifal: list[RashifalRead]
