from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas import AlmanacSection, ChoghadiyaDay, KundaliRequest, RahuKaal
from app.services import almanac as almanac_service
from app.services import jhora_gateway as gateway
from app.services.time_utils import resolve_birth_datetimes

router = APIRouter(prefix="/api/almanac", tags=["almanac"])


@router.get("/sections", response_model=list[str])
def list_sections() -> list[str]:
    """The sections the generic table page can render."""
    return sorted(almanac_service.SECTIONS)


@router.get("/choghadiya-detail", response_model=ChoghadiyaDay)
def choghadiya_detail(
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    on: date_type | None = Query(None, description="Defaults to today."),
) -> ChoghadiyaDay:
    """The dedicated choghadiya page, with day and night split out."""
    from app.services.day_tables import detailed_choghadiya

    day = on or date_type.today()
    try:
        return ChoghadiyaDay(**detailed_choghadiya(lat, lng, tz, day, label))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Choghadiya failed: {exc}") from exc


@router.get("/hora-detail", response_model=ChoghadiyaDay)
def hora_detail(
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    on: date_type | None = Query(None, description="Defaults to today."),
) -> ChoghadiyaDay:
    """The dedicated hora page. Same shape as choghadiya so one layout renders both."""
    from app.services.day_tables import detailed_hora

    day = on or date_type.today()
    try:
        return ChoghadiyaDay(**detailed_hora(lat, lng, tz, day, label))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Hora failed: {exc}") from exc


@router.get("/rahu-kaal", response_model=RahuKaal)
def rahu_kaal_detail(
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    on: date_type | None = Query(None, description="Defaults to today."),
) -> RahuKaal:
    """Rahu Kaal for a day, with the weekday wheel behind it."""
    from app.services.day_tables import rahu_kaal

    day = on or date_type.today()
    try:
        return RahuKaal(**rahu_kaal(lat, lng, tz, day, label))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rahu Kaal failed: {exc}") from exc


@router.get("/eclipse-year")
def eclipse_year(
    kind: str = Query(..., pattern="^(solar|lunar)$"),
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    year: int | None = Query(None, ge=1900, le=2200, description="Defaults to the year of the next eclipse."),
) -> dict:
    """Every solar or lunar eclipse in a year, with local timings and Sutak."""
    from app.services.eclipses import default_year, eclipses_for_year

    try:
        chosen = year or default_year(kind, tz)
        return eclipses_for_year(kind, lat, lng, tz, chosen, label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Eclipse calculation failed: {exc}") from exc


@router.get("/season")
def season_detail(
    event: str = Query(..., pattern="^(vernal-equinox|summer-solstice|autumnal-equinox|winter-solstice)$"),
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    year: int | None = Query(None, ge=1900, le=2200, description="Defaults to the current year."),
) -> dict:
    """An equinox or solstice for a year, with the day length around it."""
    from app.services.seasons import season

    try:
        return season(event, lat, lng, tz, year or date_type.today().year, label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Season calculation failed: {exc}") from exc


def _run(label: str, fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{label} failed: {exc}") from exc


@router.get("/lunar-days")
def lunar_days(
    kind: str = Query(..., pattern="^(purnima|amavasya)$"),
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    year: int | None = Query(None, ge=1900, le=2200),
) -> dict:
    """Every Purnima or Amavasya in a year, with the day it is kept on."""
    from app.services import planet_events

    return _run("Purnima/Amavasya", planet_events.lunar_days, kind, lat, lng, tz, year or date_type.today().year)


@router.get("/planet-transits")
def planet_transits(
    planet: str = Query(..., max_length=16),
    division: str = Query("rashi", pattern="^(rashi|nakshatra|pada)$"),
    tz: str = Query("Asia/Kolkata", max_length=64),
    year: int | None = Query(None, ge=1900, le=2200),
) -> dict:
    """When a graha enters each rashi, nakshatra or pada in a year."""
    from app.services import planet_events

    return _run("Transit", planet_events.transits, planet, division, tz, year or date_type.today().year)


@router.get("/planet-retrogrades")
def planet_retrogrades(
    planet: str = Query(..., max_length=16),
    tz: str = Query("Asia/Kolkata", max_length=64),
    year: int | None = Query(None, ge=1900, le=2200),
) -> dict:
    """Vakri and Margi stations of a graha in a year."""
    from app.services import planet_events

    return _run("Retrograde", planet_events.retrogrades, planet, tz, year or date_type.today().year)


@router.get("/planet-combustions")
def planet_combustions(
    planet: str = Query(..., max_length=16),
    tz: str = Query("Asia/Kolkata", max_length=64),
    year: int | None = Query(None, ge=1900, le=2200),
) -> dict:
    """Asta and Uday of a graha in a year."""
    from app.services import planet_events

    return _run("Combustion", planet_events.combustions, planet, tz, year or date_type.today().year)


@router.get("/planet-positions")
def planet_positions(
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    at: datetime | None = Query(None, description="Local date-time at the place. Defaults to now."),
    ayanamsha: str = Query("lahiri", pattern="^(lahiri|raman|kp|tropical)$"),
    true_nodes: bool = Query(False, alias="trueNodes"),
    outer: bool = Query(True),
) -> dict:
    """Every graha's sidereal position at a moment."""
    from dateutil import tz as tzlib

    from app.services import planet_events

    zone = tzlib.gettz(tz)
    if zone is None:
        raise HTTPException(status_code=400, detail="Unsupported timezone.")
    moment = at.replace(tzinfo=None) if at else datetime.now(zone).replace(tzinfo=None)
    return _run(
        "Planetary positions",
        planet_events.positions,
        lat, lng, tz, moment, ayanamsha=ayanamsha, true_nodes=true_nodes, outer=outer,
    )


@router.get("/{section}", response_model=AlmanacSection)
def get_section(
    section: str,
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
    on: date_type | None = Query(None, description="Defaults to today."),
    months: int = Query(3, ge=1, le=12, description="Range for the festivals section."),
) -> AlmanacSection:
    """Any almanac section, in one uniform columns/rows shape.

    A plain def so FastAPI runs it in a threadpool: these are CPU-bound
    ephemeris searches that would otherwise block the event loop.
    """
    builder = almanac_service.SECTIONS.get(section)
    if builder is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown section '{section}'. Available: {', '.join(sorted(almanac_service.SECTIONS))}.",
        )

    day = on or date_type.today()
    try:
        offset = gateway.utc_offset_hours(tz, day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    place = gateway.place_of(lat, lng, offset, label)
    jd = gateway.julian_day(day)

    try:
        if section in almanac_service.NATIVE_SECTIONS:
            payload = builder(lat, lng, tz, day)
        elif section == "festivals":
            payload = builder(place, jd, day, months)
        else:
            payload = builder(place, jd, day)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{section} calculation failed: {exc}") from exc

    return AlmanacSection(section=section, location=label, **payload)


@router.post("/doshas", response_model=AlmanacSection)
def get_doshas(payload: KundaliRequest) -> AlmanacSection:
    """Classical doshas for a birth chart, in the same table shape."""
    if payload.place.precision == "country":
        raise HTTPException(
            status_code=400,
            detail="Country-level birthplace is not accurate enough. Select a city or enter manual coordinates.",
        )
    try:
        local_dt, _ = resolve_birth_datetimes(
            payload.birth_date, payload.birth_time12h, payload.meridiem, payload.place.timezone
        )
        offset = gateway.utc_offset_hours(payload.place.timezone, payload.birth_date)
        place = gateway.place_of(payload.place.lat, payload.place.lng, offset, payload.place.label)
        # PyJHora takes the local birth moment plus the place's own offset.
        jd = gateway.julian_day(payload.birth_date) + (
            local_dt.hour + local_dt.minute / 60
        ) / 24 - offset / 24
        result = almanac_service.doshas(jd, place)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dosha calculation failed: {exc}") from exc

    return AlmanacSection(section="doshas", location=payload.place.label, **result)
