from fastapi import APIRouter, HTTPException

from app.schemas import PlaceSuggestion, ResolvePlaceRequest, ResolvedPlace
from app.services.geolocation import GeolocationService


def build_router(geolocation_service: GeolocationService) -> APIRouter:
    router = APIRouter(prefix="/api/places", tags=["places"])

    @router.get("/autocomplete", response_model=list[PlaceSuggestion])
    async def autocomplete_places(q: str) -> list[PlaceSuggestion]:
        try:
            return await geolocation_service.autocomplete(q)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/resolve", response_model=ResolvedPlace)
    async def resolve_place(payload: ResolvePlaceRequest) -> ResolvedPlace:
        try:
            return await geolocation_service.resolve(payload.provider, payload.provider_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router

