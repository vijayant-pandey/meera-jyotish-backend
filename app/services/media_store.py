"""Where admin-uploaded images are kept.

With CLOUDINARY_URL set, uploads go to Cloudinary and the stored URL is its
permanent https link, so they survive redeploys on hosts with a throwaway disk
(such as Render's free plan). Without it, they are written to backend/media/
and served by the app at /media/, which suits local development.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

import httpx

from app.config import get_settings

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "media"
CLOUDINARY_FOLDER = "meera-jyotish"


class MediaStoreError(RuntimeError):
    """The storage backend refused or failed the upload."""


class MediaStore(Protocol):
    async def save(self, data: bytes, extension: str, content_type: str) -> tuple[str, str]:
        """Store the bytes and return (public url, stored name)."""
        ...


class LocalMediaStore:
    def __init__(self, root: Path = MEDIA_ROOT) -> None:
        self.root = root

    async def save(self, data: bytes, extension: str, content_type: str) -> tuple[str, str]:
        # The stored name is generated, never taken from the upload, so a crafted
        # filename cannot traverse out of the media directory or overwrite anything.
        self.root.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(16)}{extension}"
        (self.root / name).write_bytes(data)
        return f"/media/{name}", name


@dataclass(frozen=True)
class CloudinaryCredentials:
    cloud_name: str
    api_key: str
    api_secret: str

    @classmethod
    def from_url(cls, url: str) -> "CloudinaryCredentials":
        """Parse cloudinary://<api_key>:<api_secret>@<cloud_name>."""
        parts = urlsplit(url.strip())
        if parts.scheme != "cloudinary" or not (parts.username and parts.password and parts.hostname):
            raise ValueError("CLOUDINARY_URL must look like cloudinary://<api_key>:<api_secret>@<cloud_name>.")
        return cls(parts.hostname, unquote(parts.username), unquote(parts.password))


def sign(params: dict[str, str], api_secret: str) -> str:
    """Cloudinary's upload signature: SHA-1 of the sorted params plus the secret."""
    payload = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha1((payload + api_secret).encode("utf-8")).hexdigest()


class CloudinaryMediaStore:
    def __init__(self, credentials: CloudinaryCredentials, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.credentials = credentials
        self.transport = transport

    async def save(self, data: bytes, extension: str, content_type: str) -> tuple[str, str]:
        name = secrets.token_hex(16)
        params = {"folder": CLOUDINARY_FOLDER, "public_id": name, "timestamp": str(int(time.time()))}
        form = {**params, "api_key": self.credentials.api_key, "signature": sign(params, self.credentials.api_secret)}
        endpoint = f"https://api.cloudinary.com/v1_1/{self.credentials.cloud_name}/image/upload"

        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                response = await client.post(endpoint, data=form, files={"file": (name + extension, data, content_type)})
        except httpx.HTTPError as exc:
            raise MediaStoreError(f"Could not reach Cloudinary: {exc}") from exc

        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code != 200 or "secure_url" not in body:
            message = (body.get("error") or {}).get("message") or f"HTTP {response.status_code}"
            raise MediaStoreError(f"Cloudinary rejected the upload: {message}")
        return body["secure_url"], body.get("public_id", name)


def get_media_store() -> MediaStore:
    """FastAPI dependency: Cloudinary when configured, the local folder otherwise."""
    url = get_settings().cloudinary_url
    if url:
        return CloudinaryMediaStore(CloudinaryCredentials.from_url(url))
    return LocalMediaStore()


__all__ = [
    "CloudinaryCredentials",
    "CloudinaryMediaStore",
    "LocalMediaStore",
    "MEDIA_ROOT",
    "MediaStore",
    "MediaStoreError",
    "get_media_store",
    "sign",
]
