from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import MatchRequest, MatchResponse
from app.services.matchmaking import compute_ashtakoota

router = APIRouter(prefix="/api/match", tags=["match"])


@router.post("/ashtakoota", response_model=MatchResponse)
def match_ashtakoota(payload: MatchRequest) -> MatchResponse:
    """Guna milan for two birth charts.

    A plain def so FastAPI runs it in a threadpool: this casts two full charts,
    which is CPU-bound ephemeris work that would otherwise block the event loop.
    """
    for label, person in (("boy", payload.boy), ("girl", payload.girl)):
        if person.place.precision == "country":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Country-level birthplace for the {label} is not accurate enough. "
                    "Select a city or enter manual coordinates."
                ),
            )

    try:
        return compute_ashtakoota(payload.boy, payload.girl)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Match calculation failed: {exc}") from exc
