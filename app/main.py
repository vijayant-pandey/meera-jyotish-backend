from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap import ensure_schema
from app.config import get_settings
from app.database import engine
from app.models import Base
from app.routers.admin import MEDIA_ROOT
from app.routers.admin import router as admin_router
from app.routers.almanac import router as almanac_router
from app.routers.auth import router as auth_router
from app.routers.content import router as content_router
from app.routers.panchang import router as panchang_router
from app.routers.health import router as health_router
from app.routers.match import router as match_router
from app.routers.places import build_router as build_places_router
from app.routers.reports import router as reports_router
from app.services.geolocation import GeolocationService


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def allow(self, key: str) -> tuple[bool, int]:
        async with self.lock:
            now = time.monotonic()
            queue = self.requests[key]
            while queue and now - queue[0] >= self.window_seconds:
                queue.popleft()
            if len(queue) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - queue[0])))
                return False, retry_after
            queue.append(now)
            return True, self.window_seconds


settings = get_settings()
rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
geolocation_service = GeolocationService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    yield


app = FastAPI(title="Kundali API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        client_host = request.client.host if request.client else "local"
        allowed, retry_after = await rate_limiter.allow(client_host)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(build_places_router(geolocation_service))
app.include_router(reports_router)
app.include_router(content_router)
app.include_router(panchang_router)
app.include_router(match_router)
app.include_router(almanac_router)
app.include_router(admin_router)

# Uploaded images are served straight from disk. The directory is created on
# startup so a fresh checkout does not fail the mount.
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")
