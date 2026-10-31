from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest

from app.services.media_store import (
    CloudinaryCredentials,
    CloudinaryMediaStore,
    LocalMediaStore,
    MediaStoreError,
    sign,
)

CREDS = CloudinaryCredentials("demo-cloud", "123456", "s3cret")


def test_credentials_parse_from_the_dashboard_url():
    creds = CloudinaryCredentials.from_url("cloudinary://123456:s3cret@demo-cloud")
    assert creds == CREDS


@pytest.mark.parametrize("bad", ["", "https://x", "cloudinary://<your_api_key>@demo", "cloudinary://key@demo"])
def test_incomplete_urls_are_rejected(bad):
    with pytest.raises(ValueError):
        CloudinaryCredentials.from_url(bad)


def test_signature_sorts_params_and_appends_the_secret():
    expected = hashlib.sha1(b"folder=f&public_id=p&timestamp=1s3cret").hexdigest()
    assert sign({"timestamp": "1", "public_id": "p", "folder": "f"}, "s3cret") == expected


def test_cloudinary_upload_returns_the_secure_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"secure_url": "https://res.cloudinary.com/demo-cloud/x.png", "public_id": "meera-jyotish/x"})

    store = CloudinaryMediaStore(CREDS, transport=httpx.MockTransport(handler))
    url, name = asyncio.run(store.save(b"png-bytes", ".png", "image/png"))

    assert url == "https://res.cloudinary.com/demo-cloud/x.png"
    assert name == "meera-jyotish/x"
    assert seen["url"] == "https://api.cloudinary.com/v1_1/demo-cloud/image/upload"
    assert b"s3cret" not in seen["body"]  # the secret only goes into the signature
    assert b"signature" in seen["body"]


def test_cloudinary_errors_surface_as_media_store_errors():
    handler = lambda request: httpx.Response(401, json={"error": {"message": "Invalid Signature"}})
    store = CloudinaryMediaStore(CREDS, transport=httpx.MockTransport(handler))
    with pytest.raises(MediaStoreError, match="Invalid Signature"):
        asyncio.run(store.save(b"x", ".png", "image/png"))


def test_local_store_writes_a_generated_name(tmp_path):
    url, name = asyncio.run(LocalMediaStore(tmp_path).save(b"abc", ".jpg", "image/jpeg"))
    assert url == f"/media/{name}" and name.endswith(".jpg")
    assert (tmp_path / name).read_bytes() == b"abc"
