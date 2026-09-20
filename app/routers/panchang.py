from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import CamelModel
from app.services.panchang import PanchangResult, compute_panchang

router = APIRouter(prefix="/api/panchang", tags=["panchang"])


class IntervalOut(CamelModel):
    name: str
    ends_at: str
    number: int = 0
    extra: str = ""


class SegmentOut(CamelModel):
    name: str
    starts_at: str
    ends_at: str
    number: int = 0
    extra: str = ""


class TimelineOut(CamelModel):
    sunrise: str
    sunset: str
    next_sunrise: str
    vara: str
    tithi: list[SegmentOut]
    nakshatra: list[SegmentOut]
    yoga: list[SegmentOut]
    karana: list[SegmentOut]
    choghadiya: list[SegmentOut]


class GrahaOut(CamelModel):
    name: str
    sanskrit: str
    sign: str
    longitude: float
    degree_in_sign: float
    motion: str
    visibility: str


class PanchangOut(CamelModel):
    location: str
    timezone: str
    moment: str
    day: str
    weekday: str
    sunrise: str
    sunset: str
    day_length: str
    vara: str
    paksha: str
    tithi: IntervalOut
    nakshatra: IntervalOut
    yoga: IntervalOut
    karanas: list[IntervalOut]
    moonsign: str
    sunsign: str
    amanta_month: str
    purnimanta_month: str
    shaka_samvat: str
    vikram_samvat: str
    gujarati_samvat: str
    pravishte: int
    ghati: int
    pal: int
    vipal: int
    timeline: TimelineOut
    grahas: list[GrahaOut]


def _interval(value) -> IntervalOut:
    return IntervalOut(
        name=value.name,
        ends_at=value.ends_at.isoformat(),
        number=value.number,
        extra=value.extra,
    )


def _segment(value) -> SegmentOut:
    return SegmentOut(
        name=value.name,
        starts_at=value.starts_at.isoformat(),
        ends_at=value.ends_at.isoformat(),
        number=value.number,
        extra=value.extra,
    )


def _timeline(value) -> TimelineOut:
    return TimelineOut(
        sunrise=value.sunrise.isoformat(),
        sunset=value.sunset.isoformat(),
        next_sunrise=value.next_sunrise.isoformat(),
        vara=value.vara,
        tithi=[_segment(s) for s in value.tithi],
        nakshatra=[_segment(s) for s in value.nakshatra],
        yoga=[_segment(s) for s in value.yoga],
        karana=[_segment(s) for s in value.karana],
        choghadiya=[_segment(s) for s in value.choghadiya],
    )


def _serialise(result: PanchangResult) -> PanchangOut:
    return PanchangOut(
        location=result.location,
        timezone=result.timezone,
        moment=result.moment.isoformat(),
        day=result.day.isoformat(),
        weekday=result.moment.strftime("%A"),
        sunrise=result.sunrise.isoformat(),
        sunset=result.sunset.isoformat(),
        day_length=result.day_length,
        vara=result.vara,
        paksha=result.paksha,
        tithi=_interval(result.tithi),
        nakshatra=_interval(result.nakshatra),
        yoga=_interval(result.yoga),
        karanas=[_interval(k) for k in result.karanas],
        moonsign=result.moonsign,
        sunsign=result.sunsign,
        amanta_month=result.amanta_month,
        purnimanta_month=result.purnimanta_month,
        shaka_samvat=result.shaka_samvat,
        vikram_samvat=result.vikram_samvat,
        gujarati_samvat=result.gujarati_samvat,
        pravishte=result.pravishte,
        ghati=result.ghati,
        pal=result.pal,
        vipal=result.vipal,
        timeline=_timeline(result.timeline),
        grahas=[
            GrahaOut(
                name=g.name, sanskrit=g.sanskrit, sign=g.sign, longitude=g.longitude,
                degree_in_sign=g.degree_in_sign, motion=g.motion, visibility=g.visibility,
            )
            for g in result.grahas
        ],
    )


@router.get("", response_model=PanchangOut)
def get_panchang(
    lat: float = Query(23.170152, ge=-90, le=90),
    lng: float = Query(79.932451, ge=-180, le=180),
    tz: str = Query("Asia/Kolkata", max_length=64),
    label: str = Query("Jabalpur, India", max_length=160),
) -> PanchangOut:
    """Panchang for right now at the given place.

    Declared as a plain def so FastAPI runs it in a threadpool: the ephemeris
    work is CPU-bound and would otherwise block the event loop.
    """
    try:
        return _serialise(compute_panchang(lat, lng, tz, label))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
