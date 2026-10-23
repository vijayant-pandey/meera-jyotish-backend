"""Almanac sections, every one returning the same columns/rows shape.

The uniform shape is the point: one frontend table component renders any
section, so adding a section later is an entry in SECTIONS plus a nav item,
not a new page.

Everything here goes through jhora_gateway, which handles the swisseph arity
shim and forces this app's Lahiri / mean-node convention.
"""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime, timedelta

from app.services import jhora_gateway as g

_TAG = re.compile(r"<[^>]+>")


def _plain(value: object) -> str:
    """PyJHora returns dosha descriptions as HTML fragments."""
    return _TAG.sub("", str(value)).replace("&nbsp;", " ").strip()


def _hhmmss_to_hhmm(value: str) -> str:
    parts = str(value).split(":")
    return f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else str(value)


# --- muhurta -----------------------------------------------------------------

# Which eighth of the daylight each of the three belongs to, indexed from
# Sunday. These are the published tables, and they are computed here rather
# than taken from PyJHora: its trikalam put Sunday's Rahu Kalam in the morning,
# which disagreed with the dedicated Rahu Kaal page on the very same screen.
_TRIKALAM_PERIODS = {
    "Rahu Kalam": [8, 2, 7, 5, 6, 4, 3],
    "Yamaganda": [5, 4, 3, 2, 1, 7, 6],
    "Gulika Kalam": [7, 6, 5, 4, 3, 2, 1],
}


def muhurta(lat: float, lng: float, tz: str, on: date_type) -> dict:
    from app.services.day_tables import _sun_times

    sunrise, sunset, _next_sunrise, _zone = _sun_times(lat, lng, tz, on)
    sunday_first = (sunrise.weekday() + 1) % 7
    eighth = (sunset - sunrise) / 8

    rows: list[dict] = []
    for label, table in _TRIKALAM_PERIODS.items():
        period = table[sunday_first]
        begins = sunrise + eighth * (period - 1)
        rows.append(
            {
                "name": label,
                "start": begins.strftime("%H:%M"),
                "end": (begins + eighth).strftime("%H:%M"),
                "quality": "Inauspicious",
            }
        )

    # The rest still come from PyJHora, which needs its own place and julian day.
    offset = g.utc_offset_hours(tz, on)
    place = g.place_of(lat, lng, offset, "")
    jd = g.julian_day(on)

    with g.jhora_context(), g.quiet():
        for label, fn, good in [
            ("Abhijit Muhurta", g.drik.abhijit_muhurta, True),
            ("Durmuhurtam", g.drik.durmuhurtam, False),
        ]:
            window = fn(jd, place)
            if window:
                rows.append(
                    {
                        "name": label,
                        "start": _hhmmss_to_hhmm(window[0]),
                        "end": _hhmmss_to_hhmm(window[1]),
                        "quality": "Auspicious" if good else "Inauspicious",
                    }
                )

        for label, fn, good in [
            ("Brahma Muhurta", g.drik.brahma_muhurtha, True),
            ("Godhuli Muhurta", g.drik.godhuli_muhurtha, True),
            ("Nishita Kaala", g.drik.nishita_kaala, True),
            ("Varjyam", g.drik.varjyam, False),
        ]:
            window = fn(jd, place)
            if window:
                rows.append(
                    {
                        "name": label,
                        "start": g.float_hours_to_hhmm(window[0]),
                        "end": g.float_hours_to_hhmm(window[1]),
                        "quality": "Auspicious" if good else "Inauspicious",
                    }
                )

        for window in g.drik.amrit_kaalam(jd, place) or []:
            rows.append(
                {
                    "name": "Amrit Kaalam",
                    "start": _hhmmss_to_hhmm(window[0]),
                    "end": _hhmmss_to_hhmm(window[1]),
                    "quality": "Auspicious",
                }
            )

    for row in rows:
        row["tone"] = "good" if row["quality"] == "Auspicious" else "bad"
    rows.sort(key=lambda row: row["start"])
    return {
        "title": "Muhurta and day timings",
        "subtitle": f"Windows for {on.isoformat()}",
        "columns": [
            {"key": "name", "label": "Period"},
            {"key": "start", "label": "From"},
            {"key": "end", "label": "To"},
            {"key": "quality", "label": "Quality"},
        ],
        "rows": rows,
        "note": (
            "Rahu Kalam, Yamaganda, Gulika and Durmuhurtam are the periods "
            "traditionally avoided. Times are local to the selected place."
        ),
    }


# --- hora and chaughadiya ------------------------------------------------------

# Chaldean descending order. Each day's first hora is that weekday's lord, and
# the sequence then steps through this list, wrapping.
_HORA_SEQUENCE = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]
# Sunday first, matching Python's weekday()+1 convention used below.
_WEEKDAY_LORDS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
# The quality word published alongside each hora lord.
_HORA_QUALITY = {
    "Sun": "Vigorous",
    "Moon": "Gentle",
    "Mars": "Aggressive",
    "Mercury": "Quick",
    "Jupiter": "Fruitful",
    "Venus": "Beneficial",
    "Saturn": "Sluggish",
}

_CHOGHADIYA_ORDER = ["Udvega", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga"]
_CHOGHADIYA_BAD = {"Udvega", "Kala", "Roga"}

# Three-way tone, so the page colours rows from the data rather than by
# pattern-matching the label. Chara and the conditional benefics are neutral
# rather than being forced into good or bad.
_CHOGHADIYA_TONE = {
    "Amrita": "good", "Shubha": "good", "Labha": "good",
    "Chara": "neutral",
    "Udvega": "bad", "Kala": "bad", "Roga": "bad",
}
_HORA_TONE = {
    "Jupiter": "good", "Venus": "good",
    "Mercury": "neutral", "Moon": "neutral",
    "Sun": "bad", "Mars": "bad", "Saturn": "bad",
}


def _sun_times(latitude: float, longitude: float, timezone_name: str, on: date_type):
    """Sunrise, sunset and the next sunrise, from this app's own ephemeris
    rather than PyJHora - the panchang page already uses these, so the hora and
    chaughadiya tables agree with it to the minute."""
    from app.services.panchang import _from_julian, _julian, _sun_event
    from dateutil import tz

    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")
    midnight = datetime(on.year, on.month, on.day, tzinfo=zone)
    sunrise_jd = _sun_event(_julian(midnight), latitude, longitude, rising=True)
    sunset_jd = _sun_event(sunrise_jd, latitude, longitude, rising=False)
    next_sunrise_jd = _sun_event(sunrise_jd + 0.5, latitude, longitude, rising=True)
    return (
        _from_julian(sunrise_jd, zone),
        _from_julian(sunset_jd, zone),
        _from_julian(next_sunrise_jd, zone),
    )


def _clock(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0")


def hora(latitude: float, longitude: float, timezone_name: str, on: date_type) -> dict:
    """Twelve horas across the daylight and twelve across the night.

    Day and night horas are each an equal division of their own span, so a hora
    is only about an hour, never exactly one.
    """
    sunrise, sunset, next_sunrise = _sun_times(latitude, longitude, timezone_name, on)

    # weekday(): Monday=0. The hora rule is stated from Sunday.
    sunday_first = (sunrise.weekday() + 1) % 7
    start_lord = _WEEKDAY_LORDS[sunday_first]
    cursor = _HORA_SEQUENCE.index(start_lord)

    rows: list[dict] = []
    for group, begins, ends in (
        ("Day Hora", sunrise, sunset),
        ("Night Hora", sunset, next_sunrise),
    ):
        width = (ends - begins) / 12
        for unit in range(12):
            lord = _HORA_SEQUENCE[cursor % 7]
            cursor += 1
            rows.append(
                {
                    "group": group,
                    "lord": lord,
                    "quality": _HORA_QUALITY[lord],
                    "start": _clock(begins + width * unit),
                    "end": _clock(begins + width * (unit + 1)),
                    "tone": _HORA_TONE[lord],
                }
            )

    return {
        "title": "Hora Muhurat",
        "subtitle": f"{on.isoformat()} - sunrise {_clock(sunrise)}, sunset {_clock(sunset)}",
        "columns": [
            {"key": "lord", "label": "Hora"},
            {"key": "quality", "label": "Nature"},
            {"key": "start", "label": "From"},
            {"key": "end", "label": "To"},
        ],
        "rows": rows,
        "note": (
            "The first hora of each day belongs to that weekday's lord, and the "
            "sequence then follows the Chaldean order. Day and night horas divide "
            "their own spans, so each is near an hour rather than exactly one."
        ),
    }


def chaughadiya(latitude: float, longitude: float, timezone_name: str, on: date_type) -> dict:
    """Eight divisions of the daylight and eight of the night.

    Same rule the panchang chart already draws, surfaced as its own table.
    """
    sunrise, sunset, next_sunrise = _sun_times(latitude, longitude, timezone_name, on)
    sunday_first = (sunrise.weekday() + 1) % 7

    rows: list[dict] = []
    for group, begins, ends, first, step in (
        ("Day Choghadiya", sunrise, sunset, sunday_first * 3, 1),
        ("Night Choghadiya", sunset, next_sunrise, (sunday_first + 4) * 3, -2),
    ):
        width = (ends - begins) / 8
        for unit in range(8):
            name = _CHOGHADIYA_ORDER[(first + step * unit) % 7]
            rows.append(
                {
                    "group": group,
                    "name": name,
                    "quality": "Inauspicious" if name in _CHOGHADIYA_BAD else "Auspicious",
                    "start": _clock(begins + width * unit),
                    "end": _clock(begins + width * (unit + 1)),
                    "tone": _CHOGHADIYA_TONE[name],
                }
            )

    return {
        "title": "Choghadiya Muhurat",
        "subtitle": f"{on.isoformat()} - sunrise {_clock(sunrise)}, sunset {_clock(sunset)}",
        "columns": [
            {"key": "name", "label": "Choghadiya"},
            {"key": "quality", "label": "Nature"},
            {"key": "start", "label": "From"},
            {"key": "end", "label": "To"},
        ],
        "rows": rows,
        "note": "Udvega, Kala and Roga are the three traditionally avoided.",
    }


# --- eclipses ----------------------------------------------------------------


def eclipses(place, jd, on: date_type) -> dict:
    rows: list[dict] = []
    with g.jhora_context(), g.quiet():
        for kind, fn in (("Solar", g.eclipse.next_solar_eclipse), ("Lunar", g.eclipse.next_lunar_eclipse)):
            try:
                result = fn(jd, place)
            except Exception:
                result = None
            if not result:
                continue
            eclipse_type, phases = result[0], result[1]
            # PyJHora pads phases that do not apply with julian day 0.
            moments = [g.ymd_hours_to_iso(*phase) for phase in phases]
            moments = [m for m in moments if m]
            if not moments:
                continue
            rows.append(
                {
                    "kind": kind,
                    "type": str(eclipse_type).title(),
                    "begins": min(moments),
                    "ends": max(moments),
                }
            )
    return {
        "title": "Next eclipses",
        "subtitle": f"Searching forward from {on.isoformat()}",
        "columns": [
            {"key": "kind", "label": "Eclipse"},
            {"key": "type", "label": "Type"},
            {"key": "begins", "label": "Begins (UTC)"},
            {"key": "ends", "label": "Ends (UTC)"},
        ],
        "rows": rows,
        "note": "Times are UTC. Visibility depends on the observer's location.",
    }


# --- retrograde planets ------------------------------------------------------

_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


def retrogrades(place, jd, on: date_type) -> dict:
    with g.jhora_context(), g.quiet():
        indices = g.drik.planets_in_retrograde(jd, place) or []
    retro = {int(i) for i in indices}
    # The nodes are always retrograde by definition; PyJHora does not always
    # list Ketu, so asserting it here keeps the table from contradicting its
    # own footnote.
    rows = [
        {
            "planet": name,
            "motion": "Vakri (retrograde)"
            if (index in retro or name in ("Rahu", "Ketu"))
            else "Margi (direct)",
            "tone": "neutral"
            if (index in retro or name in ("Rahu", "Ketu"))
            else "good",
        }
        for index, name in enumerate(_PLANETS)
        if name not in ("Sun", "Moon")
    ]
    return {
        "title": "Graha Vakri and Margi",
        "subtitle": f"Motion on {on.isoformat()}",
        "columns": [
            {"key": "planet", "label": "Graha"},
            {"key": "motion", "label": "Motion"},
        ],
        "rows": rows,
        "note": "Rahu and Ketu are always retrograde. The Sun and Moon never are.",
    }


# --- festivals and vrat ------------------------------------------------------


def festivals(place, jd, on: date_type, months: int = 3) -> dict:
    end = on + timedelta(days=30 * max(1, months))
    start_date = g.drik.Date(on.year, on.month, on.day)
    end_date = g.drik.Date(end.year, end.month, end.day)

    rows: list[dict] = []
    with g.jhora_context(), g.quiet():
        for vratha_type in g.vratha.special_vratha_map:
            try:
                found = g.vratha.special_vratha_dates(
                    place, start_date, end_date, vratha_type=vratha_type
                )
            except Exception:
                continue
            for entry in found or []:
                try:
                    (year, month, day) = entry[0]
                    label = str(entry[3]) if len(entry) > 3 else vratha_type
                except Exception:
                    continue
                rows.append(
                    {
                        "date": date_type(year, month, day).isoformat(),
                        "name": label,
                        "kind": vratha_type.replace("_", " ").title(),
                    }
                )

    rows.sort(key=lambda row: (row["date"], row["name"]))
    return {
        "title": "Vrat and festival dates",
        "subtitle": f"{on.isoformat()} to {end.isoformat()}, computed for this place",
        "columns": [
            {"key": "date", "label": "Date"},
            {"key": "kind", "label": "Observance"},
            {"key": "name", "label": "Detail"},
        ],
        "rows": rows,
        "note": (
            "Derived from tithi, nakshatra and yoga at this location rather than "
            "from a fixed list, so the dates shift correctly with the place."
        ),
    }


# --- registry ----------------------------------------------------------------

# These compute from this app's own ephemeris and take (lat, lng, tz, date).
# Everything else goes through PyJHora and takes (place, jd, date).
NATIVE_SECTIONS = {"hora", "chaughadiya", "muhurta"}

SECTIONS = {
    "muhurta": muhurta,
    "hora": hora,
    "chaughadiya": chaughadiya,
    "eclipses": eclipses,
    "retrogrades": retrogrades,
    "festivals": festivals,
}


def _verdict(value: object) -> bool:
    """The structured dosha functions return either a bool or a list/tuple whose
    first element is the verdict."""
    if isinstance(value, (list, tuple)):
        return bool(value[0]) if value else False
    return bool(value)


def doshas(jd: float, place) -> dict:
    """Doshas for a birth chart.

    The presence of each dosha comes from PyJHora's structured functions, which
    return booleans. Its get_dosha_details() aggregate is used only for the
    explanatory prose: that text is largely definitional, so deciding presence
    from it (by looking for "there is no") produces false positives - Manglik
    and Pitru both return a definition with no verdict in the text at all.
    """
    from jhora import utils as jhora_utils
    from jhora.horoscope.chart import charts as jhora_charts
    from jhora.horoscope.chart import dosha as jhora_dosha

    with g.jhora_context(), g.quiet():
        positions = jhora_charts.divisional_chart(jd, place, divisional_chart_factor=1)
        house_to_planet = jhora_utils.get_house_planet_list_from_planet_positions(positions)
        moon_sign, moon_degree = positions[2][1]
        moon_longitude = moon_sign * 30 + moon_degree
        moon_star = int(moon_longitude * 27 / 360) + 1

        checks: list[tuple[str, object]] = []
        def run(label: str, fn, *args):
            try:
                checks.append((label, fn(*args)))
            except Exception:
                checks.append((label, None))

        run("Kala Sarpa Dosha", jhora_dosha.kala_sarpa, house_to_planet)
        run("Manglik Dosha", jhora_dosha.manglik, positions)
        run("Pitru Dosha", jhora_dosha.pitru_dosha, positions)
        run("Guru Chandala Dosha", jhora_dosha.guru_chandala_dosha, positions)
        run("Ganda Moola Dosha", jhora_dosha.ganda_moola, moon_star)
        run("Kalathra Dosha", jhora_dosha.kalathra, positions)
        run("Ghata Dosha", jhora_dosha.ghata, positions)
        run("Shrapit Dosha", jhora_dosha.shrapit, positions)

        try:
            prose = jhora_dosha.get_dosha_details(jd, place) or {}
        except Exception:
            prose = {}

    rows = []
    for label, raw in checks:
        if raw is None:
            status = "Not determined"
        else:
            status = "Present" if _verdict(raw) else "Not present"
        rows.append(
            {
                "name": label,
                "present": status,
                "detail": _plain(prose.get(label, "")),
                "tone": {"Present": "bad", "Not present": "good"}.get(status, "neutral"),
            }
        )

    return {
        "title": "Dosha analysis",
        "subtitle": "Classical doshas assessed for this chart",
        "columns": [
            {"key": "name", "label": "Dosha"},
            {"key": "present", "label": "Status"},
            {"key": "detail", "label": "Reading"},
        ],
        "rows": rows,
        "note": (
            "Manglik and Ganda Moola are the two most often weighed in marriage "
            "matching. A dosha is one factor in a reading, not a verdict."
        ),
    }
