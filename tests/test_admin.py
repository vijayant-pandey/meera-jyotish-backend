from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin_auth import create_admin_user
from app.database import get_db
from app.main import app
from app.models import Base

PASSWORD = "correct-horse-battery"
SHORT_OK = "vkp12311"  # 8 chars: the documented minimum


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    # A throwaway SQLite database so the tests never touch the real one.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    setup = TestingSession()
    create_admin_user(setup, "admin", "Site Admin", PASSWORD)
    setup.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_in(client: TestClient) -> None:
    response = client.post("/api/admin/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text


def test_admin_endpoints_reject_anonymous_callers(client: TestClient) -> None:
    assert client.get("/api/admin/me").status_code == 401
    assert client.get("/api/admin/content/astrologers").status_code == 401
    assert client.post("/api/admin/content/astrologers", json={"name": "X"}).status_code == 401


def test_a_public_user_session_cannot_reach_the_admin_api(client: TestClient) -> None:
    # Register a normal site user, then try the admin API with that cookie.
    registered = client.post(
        "/api/auth/register",
        json={
            "name": "Normal User",
            "email": "user@example.com",
            "phone": "9990001111",
            "password": "user-password",
        },
    )
    assert registered.status_code == 200, registered.text
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/admin/me").status_code == 401


def test_an_eight_character_password_is_accepted_end_to_end(client: TestClient) -> None:
    # Guards the pair of length rules: one on account creation, one on the login
    # schema. They were out of step before, which let an account be created that
    # could then never sign in.
    from app.admin_auth import create_admin_user
    from app.database import get_db

    db = next(app.dependency_overrides[get_db]())
    create_admin_user(db, "vijayant", "Vijayant", SHORT_OK)
    response = client.post("/api/admin/login", json={"username": "vijayant", "password": SHORT_OK})
    assert response.status_code == 200, response.text
    assert client.get("/api/admin/me").json()["username"] == "vijayant"


def test_admin_login_rejects_a_wrong_password(client: TestClient) -> None:
    response = client.post("/api/admin/login", json={"username": "admin", "password": "wrong-password"})
    assert response.status_code == 401
    assert "Invalid admin" in response.json()["detail"]


def test_astrologer_crud_round_trip(client: TestClient) -> None:
    sign_in(client)
    payload = {
        "name": "Astro Rajneesh",
        "languages": ["Hindi", "English", "Punjabi"],
        "skills": ["Vedic", "Numerology", "Tarot"],
        "rating": 4.0,
        "experienceYears": 5,
        "orders": 2045,
        "pricePerMinute": 6,
        "trending": True,
        "chatEnabled": True,
        "callEnabled": False,
    }
    created = client.post("/api/admin/content/astrologers", json=payload)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["languages"] == ["Hindi", "English", "Punjabi"]
    assert row["trending"] is True
    assert row["callEnabled"] is False

    updated = client.put(
        f"/api/admin/content/astrologers/{row['id']}",
        json={**payload, "trending": False, "skills": ["Vedic"]},
    )
    assert updated.status_code == 200
    assert updated.json()["trending"] is False
    assert updated.json()["skills"] == ["Vedic"]

    assert client.delete(f"/api/admin/content/astrologers/{row['id']}").status_code == 204
    assert client.get("/api/admin/content/astrologers").json() == []


def test_unpublished_rows_are_never_sent_to_the_public_endpoint(client: TestClient) -> None:
    sign_in(client)
    client.post(
        "/api/admin/content/astrologers",
        json={"name": "Visible", "published": True},
    )
    client.post(
        "/api/admin/content/astrologers",
        json={"name": "Hidden", "published": False},
    )

    public = client.get("/api/content").json()
    names = [a["name"] for a in public["astrologers"]]
    assert names == ["Visible"]


def test_reorder_sets_positions(client: TestClient) -> None:
    sign_in(client)
    ids = [
        client.post("/api/admin/content/services", json={"title": title}).json()["id"]
        for title in ("A", "B", "C")
    ]
    assert client.post(
        "/api/admin/content/services/reorder", json={"ids": [ids[2], ids[0], ids[1]]}
    ).status_code == 200
    titles = [row["title"] for row in client.get("/api/admin/content/services").json()]
    assert titles == ["C", "A", "B"]


def test_unknown_content_type_is_a_404(client: TestClient) -> None:
    sign_in(client)
    assert client.get("/api/admin/content/not-a-thing").status_code == 404


def test_media_upload_accepts_an_image_and_rejects_other_types(client: TestClient) -> None:
    sign_in(client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    ok = client.post(
        "/api/admin/media", files={"file": ("photo.png", io.BytesIO(png), "image/png")}
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["url"].startswith("/media/")
    # The stored name is generated, never taken from the upload.
    assert "photo" not in body["filename"]

    bad = client.post(
        "/api/admin/media",
        files={"file": ("payload.svg", io.BytesIO(b"<html>"), "text/html")},
    )
    assert bad.status_code == 400


def test_logout_invalidates_the_admin_session(client: TestClient) -> None:
    sign_in(client)
    assert client.get("/api/admin/me").status_code == 200
    assert client.post("/api/admin/logout").status_code == 200
    assert client.get("/api/admin/me").status_code == 401
