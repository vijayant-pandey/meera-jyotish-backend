"""Solar and lunar eclipses for a year, with local circumstances for a place.

The global search (sol_eclipse_when_glob / lun_eclipse_when) enumerates every
eclipse in the year. Local detail then comes from two different sources,
because the two kinds of eclipse behave differently:

- A solar eclipse is seen differently from every point, so its contacts,
  magnitude and visibility are recomputed for the place. sol_eclipse_when_loc
  returns the next eclipse visible from the place; when that is not the one the
  global search found, this eclipse cannot be seen from here at all.
- A lunar eclipse happens at the same instant for everyone. Only whether the
  Moon is above the horizon differs, so the global contact times are kept and
  the Moon's altitude is checked at each of them.

Sutak follows the common convention: it starts four prahars (12 hours) before
a solar eclipse and three prahars (9 hours) before a lunar one, counted from
the first visible contact, and ends with the eclipse. It applies only where the
eclipse is visible, and never to a penumbral-only lunar eclipse.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta, timezone

import swisseph as swe
from dateutil import tz

from app.services.panchang import _ephemeris_ready

_FLAGS = swe.FLG_SWIEPH

# Hours before the first visible contact, for adults and then for children,
# the elderly and the sick.
_SUTAK_HOURS = {"solar": (12.0, 4.5), "lunar": (9.0, 3.0)}

_SOLAR_TYPES = [
    (swe.ECL_HYBRID, "Hybrid"),
    (swe.ECL_TOTAL, "Total"),
    (swe.ECL_ANNULAR, "Annular"),
    (swe.ECL_PARTIAL, "Partial"),
]
_LUNAR_TYPES = [
    (swe.ECL_TOTAL, "Total"),
    (swe.ECL_PARTIAL, "Partial"),
    (swe.ECL_PENUMBRAL, "Penumbral"),
]


def _type_of(flags: int, table: list[tuple[int, str]]) -> str:
    for bit, name in table:
        if flags & bit:
            return name
    return "Partial"


def _moment(jd: float, zone) -> datetime | None:
    """swisseph reports an absent contact as 0."""
    if not jd or jd < 1:
        return None
    year, month, day, hours = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=hours)
    return base.astimezone(zone).replace(microsecond=0)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _duration(start: datetime | None, end: datetime | None) -> str | None:
    if not start or not end or end <= start:
        return None
    seconds = int((end - start).total_seconds())
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d} Hours {minutes:02d} Mins {secs:02d} Secs"


def _julian(moment: datetime) -> float:
    utc = moment.astimezone(timezone.utc)
    hours = utc.hour + utc.minute / 60 + utc.second / 3600
    return swe.julday(utc.year, utc.month, utc.day, hours, swe.GREG_CAL)


def _sutak(kind: str, start: datetime | None, end: datetime | None) -> dict | None:
    if not start or not end:
        return None
    adults, others = _SUTAK_HOURS[kind]
    return {
        "begins": _iso(start - timedelta(hours=adults)),
        "ends": _iso(end),
        "kidsBegins": _iso(start - timedelta(hours=others)),
        "kidsEnds": _iso(end),
    }


def _contact(label: str, moment: datetime | None, visible: bool | None = None) -> dict | None:
    if not moment:
        return None
    return {"label": label, "time": _iso(moment), "visible": visible}


def _rise_set(body: int, start_jd: float, end_jd: float, geopos, zone) -> list[dict]:
    """Rising or setting of the body while the eclipse is in progress."""
    events = []
    for flag, label in ((swe.CALC_RISE, "rise"), (swe.CALC_SET, "set")):
        try:
            result = swe.rise_trans(start_jd, body, flag, geopos, 0, 0, _FLAGS)
        except swe.Error:
            continue
        jd = result[1][0]
        if result[0] == 0 and start_jd < jd < end_jd:
            events.append({"event": label, "time": _iso(_moment(jd, zone))})
    return events


# --- solar --------------------------------------------------------------------


def _solar(glob_flags: int, glob: tuple, geopos, zone) -> dict:
    global_type = _type_of(glob_flags, _SOLAR_TYPES)
    global_max = _moment(glob[0], zone)

    entry: dict = {
        "kind": "solar",
        "globalType": global_type,
        "title": f"{global_type} Solar Eclipse",
        "date": global_max.date().isoformat(),
        "weekday": global_max.strftime("%A"),
        "globalMaximum": _iso(global_max),
        "globalBegins": _iso(_moment(glob[2], zone)),
        "globalEnds": _iso(_moment(glob[3], zone)),
        "visible": False,
        "localType": None,
        "contacts": [],
        "durations": [],
        "magnitudes": [],
        "horizonEvents": [],
        "sutak": None,
    }

    try:
        flags, local, attr = swe.sol_eclipse_when_loc(glob[0] - 1, geopos, _FLAGS)
    except swe.Error:
        flags = 0
    # The local search skips eclipses this place cannot see. If it landed on a
    # later one, this eclipse is not visible from here.
    if not flags or abs(local[0] - glob[0]) > 0.5 or not flags & swe.ECL_VISIBLE:
        entry["visibility"] = "Eclipse would not be visible from this place."
        return entry

    local_type = _type_of(flags, _SOLAR_TYPES[1:])
    first, second, maximum, third, fourth = (
        _moment(local[1], zone),
        _moment(local[2], zone),
        _moment(local[0], zone),
        _moment(local[3], zone),
        _moment(local[4], zone),
    )
    central = "Annular" if local_type == "Annular" else "Total"
    contacts = [
        _contact("Partial Eclipse Begins", first, bool(flags & swe.ECL_1ST_VISIBLE)),
        _contact(f"{central} Phase Begins", second, bool(flags & swe.ECL_2ND_VISIBLE)),
        _contact("Maximum Eclipse", maximum, bool(flags & swe.ECL_MAX_VISIBLE)),
        _contact(f"{central} Phase Ends", third, bool(flags & swe.ECL_3RD_VISIBLE)),
        _contact("Partial Eclipse Ends", fourth, bool(flags & swe.ECL_4TH_VISIBLE)),
    ]
    horizon = _rise_set(swe.SUN, local[1], local[4], geopos, zone)

    # What can actually be watched: from the first contact or sunrise, to the
    # last contact or sunset, whichever is narrower.
    seen_from = first
    seen_to = fourth
    for event in horizon:
        when = datetime.fromisoformat(event["time"])
        if event["event"] == "rise":
            seen_from = when
        else:
            seen_to = when

    entry.update(
        {
            "visible": True,
            "localType": local_type,
            "date": maximum.date().isoformat(),
            "weekday": maximum.strftime("%A"),
            "visibility": f"{local_type} solar eclipse visible from this place."
            + (" The Sun rises eclipsed." if any(e["event"] == "rise" for e in horizon) else "")
            + (" The Sun sets eclipsed." if any(e["event"] == "set" for e in horizon) else ""),
            "contacts": [c for c in contacts if c],
            "durations": [
                d
                for d in (
                    {"label": "Duration of Eclipse", "value": _duration(first, fourth)},
                    {"label": f"Duration of {central} Phase", "value": _duration(second, third)},
                    {"label": "Visible Duration", "value": _duration(seen_from, seen_to)}
                    if horizon
                    else None,
                )
                if d and d["value"]
            ],
            "magnitudes": [
                {"label": "Magnitude of Eclipse", "value": f"{attr[8]:.3f}"},
                {"label": "Obscuration of the Sun", "value": f"{attr[2] * 100:.1f}%"},
                {"label": "Sun's Altitude at Maximum", "value": f"{attr[5]:.1f}°"},
            ],
            "horizonEvents": horizon,
            "sutak": _sutak("solar", seen_from, seen_to),
        }
    )
    return entry


# --- lunar --------------------------------------------------------------------


def _moon_altitude(jd: float, geopos) -> float:
    return swe.lun_eclipse_how(jd, geopos, _FLAGS)[1][5]


def _lunar(glob_flags: int, glob: tuple, geopos, zone) -> dict:
    eclipse_type = _type_of(glob_flags, _LUNAR_TYPES)
    jd_max = glob[0]
    attr = swe.lun_eclipse_how(jd_max, geopos, _FLAGS)[1]
    umbral_mag, penumbral_mag = attr[0], attr[1]

    names = [
        (6, "First Contact with Penumbra"),
        (2, "First Contact with Umbra"),
        (4, "Total Phase Begins"),
        (0, "Maximum Eclipse"),
        (5, "Total Phase Ends"),
        (3, "Last Contact with Umbra"),
        (7, "Last Contact with Penumbra"),
    ]
    contacts = []
    for index, label in names:
        jd = glob[index]
        if jd and jd > 1:
            contacts.append(_contact(label, _moment(jd, zone), _moon_altitude(jd, geopos) > 0))

    p1, u1, u2, maximum, u3, u4, p4 = (_moment(glob[i], zone) for i, _ in names)
    horizon = _rise_set(swe.MOON, glob[6], glob[7], geopos, zone)

    # The umbral phase is the eclipse that matters for observance; it is
    # visible when the Moon is up for any part of it.
    umbral_visible = False
    if u1 and u4:
        steps = 24
        span = glob[3] - glob[2]
        umbral_visible = any(
            _moon_altitude(glob[2] + span * k / steps, geopos) > 0 for k in range(steps + 1)
        )
    penumbral_visible = any(
        _moon_altitude(glob[6] + (glob[7] - glob[6]) * k / 24, geopos) > 0 for k in range(25)
    )

    if eclipse_type == "Penumbral":
        visibility = (
            "Penumbral eclipse only, with no umbral phase. A penumbral eclipse is too faint "
            "to see with the naked eye."
        )
        if not penumbral_visible:
            visibility = "Eclipse would not be visible from this place."
    elif umbral_visible:
        visibility = f"{eclipse_type} lunar eclipse visible from this place."
        if any(e["event"] == "rise" for e in horizon):
            visibility += " The Moon rises eclipsed."
        if any(e["event"] == "set" for e in horizon):
            visibility += " The Moon sets eclipsed."
    else:
        visibility = "Eclipse would not be visible from this place."

    date = maximum.date()
    durations = [
        {"label": "Duration of Total Phase", "value": _duration(u2, u3)},
        {"label": "Duration of Umbral Phase", "value": _duration(u1, u4)},
        {"label": "Duration of Penumbral Phase", "value": _duration(p1, p4)},
    ]
    magnitudes = [{"label": "Magnitude of Penumbral Eclipse", "value": f"{penumbral_mag:.3f}"}]
    if umbral_mag > 0:
        magnitudes.insert(0, {"label": "Magnitude of Umbral Eclipse", "value": f"{umbral_mag:.3f}"})

    return {
        "kind": "lunar",
        "globalType": eclipse_type,
        "localType": eclipse_type if (umbral_visible or penumbral_visible) else None,
        "title": f"{eclipse_type} Lunar Eclipse",
        "date": date.isoformat(),
        "weekday": maximum.strftime("%A"),
        "globalMaximum": _iso(maximum),
        "globalBegins": _iso(p1),
        "globalEnds": _iso(p4),
        "visible": umbral_visible or (eclipse_type == "Penumbral" and penumbral_visible),
        "visibility": visibility,
        "contacts": [c for c in contacts if c],
        "durations": [d for d in durations if d["value"]],
        "magnitudes": magnitudes,
        "horizonEvents": horizon,
        "sutak": _sutak("lunar", u1, u4) if umbral_visible else None,
    }


# --- the year -----------------------------------------------------------------


def _next_global(kind: str, jd: float, backwards: bool = False) -> tuple[int, tuple]:
    if kind == "solar":
        return swe.sol_eclipse_when_glob(jd, _FLAGS, 0, backwards)
    return swe.lun_eclipse_when(jd, _FLAGS, 0, backwards)


def eclipses_for_year(
    kind: str, latitude: float, longitude: float, timezone_name: str, year: int, label: str
) -> dict:
    if kind not in ("solar", "lunar"):
        raise ValueError("kind must be 'solar' or 'lunar'.")
    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")
    _ephemeris_ready()
    geopos = (longitude, latitude, 0)

    start = _julian(datetime(year, 1, 1, tzinfo=zone))
    end = _julian(datetime(year + 1, 1, 1, tzinfo=zone))
    build = _solar if kind == "solar" else _lunar

    found = []
    jd = start
    while True:
        flags, glob = _next_global(kind, jd)
        if glob[0] >= end:
            following = glob
            break
        found.append(build(flags, glob, geopos, zone))
        jd = glob[0] + 1

    _, before = _next_global(kind, start, backwards=True)
    previous_max = _moment(before[0], zone)
    following_max = _moment(following[0], zone)

    today = datetime.now(zone)
    upcoming = next(
        (e["date"] for e in found if datetime.fromisoformat(e["globalEnds"]) >= today), None
    )

    return {
        "kind": kind,
        "year": year,
        "location": label,
        "timezone": timezone_name,
        "eclipses": found,
        "upcoming": upcoming,
        "previous": previous_max.date().isoformat() if previous_max else None,
        "next": following_max.date().isoformat() if following_max else None,
        "note": (
            "All times are local to the selected place, adjusted for daylight saving where it "
            "applies. Times past midnight belong to the next calendar date. An eclipse that "
            "spans two dates is listed on the date of its maximum."
        ),
    }


def default_year(kind: str, timezone_name: str) -> int:
    """The year of the next eclipse, so the page opens on one that is still to
    come, the way a visitor late in the year expects."""
    zone = tz.gettz(timezone_name) or timezone.utc
    _ephemeris_ready()
    now = datetime.now(zone)
    _, glob = _next_global(kind, _julian(now))
    moment = _moment(glob[0], zone)
    return moment.year if moment else now.year


__all__ = ["eclipses_for_year", "default_year"]
