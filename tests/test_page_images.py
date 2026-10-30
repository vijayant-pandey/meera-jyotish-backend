from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin_auth import create_admin_user
from app.database import get_db
from app.main import app
from app.models import Base, HeroSlide, PageImage
from app.page_images import SLOTS, sync_defaults

PASSWORD = "correct-horse-battery"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as setup:
        create_admin_user(setup, "admin", "Site Admin", PASSWORD)
        sync_defaults(setup)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_every_slot_is_seeded_once_with_its_built_in_image(session_factory) -> None:
    with session_factory() as db:
        sync_defaults(db)
        sync_defaults(db)
        rows = {row.key: row for row in db.query(PageImage)}
    assert set(rows) == {key for key, _label, _url in SLOTS}
    assert rows["banner.solar-eclipse"].image_url == "/images/photos/solar-eclipse.jpg"
    assert rows["zodiac.aries"].image_url == "/images/zodiac/aries.svg"


def test_an_admin_choice_survives_the_next_start(session_factory) -> None:
    with session_factory() as db:
        sync_defaults(db)
        row = db.query(PageImage).filter_by(key="banner.hora").one()
        row.image_url = "/media/custom.jpg"
        db.commit()
        sync_defaults(db)
        assert db.query(PageImage).filter_by(key="banner.hora").one().image_url == "/media/custom.jpg"


def test_empty_content_images_are_filled_with_the_built_in_picture(session_factory) -> None:
    with session_factory() as db:
        db.add(HeroSlide(id="h1", title="Birth Chart", text="", image_url=""))
        db.add(HeroSlide(id="h2", title="Something New", text="", image_url=""))
        db.commit()
        sync_defaults(db)
        slides = {row.title: row.image_url for row in db.query(HeroSlide)}
    assert slides["Birth Chart"] == "/images/photos/brihajjataka.jpg"
    # A slide the admin added has no built-in picture, so it is left alone.
    assert slides["Something New"] == ""


def test_admin_replaces_a_banner_and_the_public_site_sees_it(client: TestClient) -> None:
    assert client.post("/api/admin/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    rows = client.get("/api/admin/content/page-images").json()
    target = next(row for row in rows if row["key"] == "banner.solar-eclipse")
    updated = client.put(
        f"/api/admin/content/page-images/{target['id']}",
        json={**target, "imageUrl": "/media/eclipse.jpg", "credit": "Photo: Ravi Kumar"},
    )
    assert updated.status_code == 200, updated.text

    public = client.get("/api/content").json()["pageImages"]
    shown = next(row for row in public if row["key"] == "banner.solar-eclipse")
    assert shown["imageUrl"] == "/media/eclipse.jpg"
    assert shown["credit"] == "Photo: Ravi Kumar"
