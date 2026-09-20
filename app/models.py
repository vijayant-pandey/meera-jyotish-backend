from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reports: Mapped[list["KundaliReportModel"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="sessions")


class AdminUser(Base):
    """Site administrators, kept separate from the public `users` table so that a
    normal account can never be escalated into an admin one."""

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["AdminSession"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    admin: Mapped[AdminUser] = relationship(back_populates="sessions")


class ContentMixin:
    """Shared columns for every editable content row."""

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Astrologer(ContentMixin, Base):
    __tablename__ = "astrologers"

    name: Mapped[str] = mapped_column(String(120))
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    languages: Mapped[str] = mapped_column(Text, default="")        # comma separated
    skills: Mapped[str] = mapped_column(Text, default="")           # comma separated
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    price_per_minute: Mapped[int] = mapped_column(Integer, default=0)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    call_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trending: Mapped[bool] = mapped_column(Boolean, default=False)
    online: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceCard(ContentMixin, Base):
    __tablename__ = "service_cards"

    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    action_label: Mapped[str] = mapped_column(String(80), default="Coming Soon")
    target_route: Mapped[str] = mapped_column(String(200), default="")


class HeroSlide(ContentMixin, Base):
    __tablename__ = "hero_slides"

    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")


class NavItem(ContentMixin, Base):
    __tablename__ = "nav_items"

    label: Mapped[str] = mapped_column(String(120))
    page: Mapped[str] = mapped_column(String(60), default="coming-soon")
    coming_soon_title: Mapped[str] = mapped_column(String(160), default="")
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    # Label of the top-level item this sits under. Blank means it IS top level.
    # Stored as a label rather than an id so the admin form stays a plain text
    # field instead of asking someone to paste a row id.
    parent_label: Mapped[str] = mapped_column(String(120), default="", index=True)


class SiteText(ContentMixin, Base):
    """Free-form copy addressed by a stable key, e.g. "home.hero.heading"."""

    __tablename__ = "site_texts"

    key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    value: Mapped[str] = mapped_column(Text, default="")


class ZodiacOverride(ContentMixin, Base):
    """Per-rashi editable copy. Anything left blank falls back to the built-in
    reference data, so the derived facts stay authoritative."""

    __tablename__ = "zodiac_overrides"

    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    tagline: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    career: Mapped[str] = mapped_column(Text, default="")
    relationships: Mapped[str] = mapped_column(Text, default="")
    health: Mapped[str] = mapped_column(Text, default="")
    finance: Mapped[str] = mapped_column(Text, default="")


class Festival(ContentMixin, Base):
    """Upavas and festivals. Editable in the admin panel today; the intention is a
    rules engine keyed to tithi/nakshatra/month later, which is why the date is a
    plain column rather than anything derived."""

    __tablename__ = "festivals"

    name: Mapped[str] = mapped_column(String(200))
    occurs_on: Mapped[str] = mapped_column(String(10), default="")     # YYYY-MM-DD
    image_url: Mapped[str] = mapped_column(String(500), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class PlanetaryEvent(ContentMixin, Base):
    __tablename__ = "planetary_events"

    title: Mapped[str] = mapped_column(String(240))
    occurs_at: Mapped[str] = mapped_column(String(25), default="")     # ISO datetime
    note: Mapped[str] = mapped_column(Text, default="")


class Rashifal(ContentMixin, Base):
    __tablename__ = "rashifal"

    sign: Mapped[str] = mapped_column(String(40), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")


class Subscriber(ContentMixin, Base):
    """Footer newsletter sign-ups. Read-only in the admin panel."""

    __tablename__ = "subscribers"

    email: Mapped[str] = mapped_column(String(255), index=True)


class FeedbackMessage(ContentMixin, Base):
    """Footer feedback box."""

    __tablename__ = "feedback_messages"

    message: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(255), default="")


class KundaliReportModel(Base):
    __tablename__ = "kundali_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    request_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="reports")

