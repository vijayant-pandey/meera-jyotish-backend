"""Yearly planetary events and the sidereal positions table.

- Purnima and Amavasya: each full and new moon tithi in a year, with the day
  it is observed and its lunar month.
- Gochara: when a graha enters each rashi, nakshatra or nakshatra pada.
- Vakri and Margi: the stations where a graha turns retrograde and direct.
- Asta and Uday: when a graha comes within its classical combustion orb of the
  Sun and when it leaves it.
- Positions: every graha at a moment, with nakshatra, KP sub lord, latitude,
  speed and equatorial coordinates.

Everything is sidereal (Lahiri, mean nodes), the app's convention, except where
the positions table is explicitly asked for another ayanamsha. Event times are
found by sampling and then bisecting to the second.
"""

from __future__ import annotations

import math
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

import swisseph as swe
from dateutil import tz

from app.services.astrology import (
    COMBUSTION_ORBS,
    COMBUSTION_ORBS_RETROGRADE,
    DASHA_SEQUENCE,
    is_combust,
    nakshatra_index_and_fraction,
    planet_dignity,
    planet_relation,
    sub_lord,
)
from app.services.panchang import (
    LUNAR_MONTHS,
    NAKSHATRA_NAMES,
    SIGN_NAMES,
    _ephemeris_ready,
    _sun_event,
)

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

# key -> (English, Sanskrit, swisseph body). Ketu is derived from Rahu.
PLANETS = {
    "surya": ("Sun", "Surya", swe.SUN),
    "chandra": ("Moon", "Chandra", swe.MOON),
    "mangal": ("Mars", "Mangal", swe.MARS),
    "budha": ("Mercury", "Budha", swe.MERCURY),
    "guru": ("Jupiter", "Guru", swe.JUPITER),
    "shukra": ("Venus", "Shukra", swe.VENUS),
    "shani": ("Saturn", "Shani", swe.SATURN),
    "rahu": ("Rahu", "Rahu", swe.MEAN_NODE),
    "ketu": ("Ketu", "Ketu", swe.MEAN_NODE),
    "arun": ("Uranus", "Arun", swe.URANUS),
    "varun": ("Neptune", "Varun", swe.NEPTUNE),
    "yama": ("Pluto", "Yama", swe.PLUTO),
}
RETROGRADE_PLANETS = ["mangal", "budha", "guru", "shukra", "shani", "arun", "varun", "yama"]
ASTA_PLANETS = ["chandra", "mangal", "budha", "guru", "shukra", "shani"]

PADA_NAMES = ["First", "Second", "Third", "Fourth"]
NAKSHATRA_LORDS_SANSKRIT = {
    "Ketu": "Ketu", "Venus": "Shukra", "Sun": "Surya", "Moon": "Chandra", "Mars": "Mangal",
    "Rahu": "Rahu", "Jupiter": "Guru", "Saturn": "Shani", "Mercury": "Budha",
}


# --- time helpers -------------------------------------------------------------


def _zone(timezone_name: str):
    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")
    return zone


def _julian(moment: datetime) -> float:
    utc = moment.astimezone(timezone.utc)
    hours = utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9
    return swe.julday(utc.year, utc.month, utc.day, hours, swe.GREG_CAL)


def _moment(jd: float, zone) -> datetime:
    year, month, day, hours = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=hours)
    return base.astimezone(zone).replace(microsecond=0)


def _iso(jd: float, zone) -> str:
    return _moment(jd, zone).isoformat()


def _year_bounds(year: int, zone) -> tuple[float, float]:
    return (
        _julian(datetime(year, 1, 1, tzinfo=zone)),
        _julian(datetime(year + 1, 1, 1, tzinfo=zone)),
    )


def _bisect(predicate, low: float, high: float, seconds: float = 1.0) -> float:
    """The moment predicate flips from its value at low, to within a second."""
    start = predicate(low)
    while (high - low) * 86400 > seconds:
        mid = (low + high) / 2
        if predicate(mid) == start:
            low = mid
        else:
            high = mid
    return high


# --- positions ----------------------------------------------------------------


def _position(key: str, jd: float, flags: int = swe.FLG_SIDEREAL) -> tuple[float, float, float]:
    """(longitude, latitude, speed) for a graha."""
    body = PLANETS[key][2]
    values = swe.calc_ut(jd, body, _FLAGS | flags)[0]
    longitude, latitude, speed = values[0] % 360, values[1], values[3]
    if key == "ketu":
        longitude = (longitude + 180) % 360
        latitude = -latitude
    return longitude, latitude, speed


def _longitude(key: str, jd: float) -> float:
    return _position(key, jd)[0]


def _speed(key: str, jd: float) -> float:
    return _position(key, jd)[2]


# --- gochara (transits) -------------------------------------------------------

_DIVISIONS = {
    "rashi": 12,
    "nakshatra": 27,
    "pada": 108,
}
# Sampling step in days, short enough that no graha crosses two boundaries of
# the finest division (a pada is 3 deg 20 min) between samples.
_STEP = {
    "chandra": 1 / 24, "surya": 0.25, "budha": 0.25, "shukra": 0.25, "mangal": 0.5,
    "rahu": 1.0, "ketu": 1.0, "guru": 1.0, "shani": 1.0, "arun": 2.0, "varun": 2.0, "yama": 2.0,
}


def _division_index(longitude: float, parts: int) -> int:
    # Scale before splitting so exact boundary degrees land in the right part,
    # the same care nakshatra_index_and_fraction takes.
    return min(int(longitude * parts / 360), parts - 1)


def _division_label(index: int, division: str) -> dict:
    if division == "rashi":
        return {"name": SIGN_NAMES[index], "sign": index + 1}
    if division == "nakshatra":
        return {"name": NAKSHATRA_NAMES[index], "nakshatra": index + 1}
    nakshatra, pada = divmod(index, 4)
    return {
        "name": f"{NAKSHATRA_NAMES[nakshatra]} {PADA_NAMES[pada]} Pada",
        "nakshatra": nakshatra + 1,
        "pada": pada + 1,
        "sign": index // 9 + 1,
    }


def transits(key: str, division: str, timezone_name: str, year: int) -> dict:
    if key not in PLANETS:
        raise ValueError(f"Unknown graha '{key}'.")
    if division not in _DIVISIONS:
        raise ValueError(f"Unknown division '{division}'.")
    zone = _zone(timezone_name)
    _ephemeris_ready()
    parts = _DIVISIONS[division]
    start, end = _year_bounds(year, zone)
    step = _STEP[key]

    index_at = lambda jd: _division_index(_longitude(key, jd), parts)  # noqa: E731
    entries = []
    jd = start
    current = index_at(jd)
    initial = current
    while jd < end:
        nxt = min(jd + step, end)
        index = index_at(nxt)
        if index != current:
            when = _bisect(lambda t: index_at(t) == current, jd, nxt)
            entered = index_at(when)
            entries.append(
                {
                    **_division_label(entered, division),
                    "time": _iso(when, zone),
                    "retrograde": _speed(key, when) < 0,
                }
            )
            current = entered
            jd = when
            continue
        jd = nxt

    now = _julian(datetime.now(zone))
    now_index = index_at(now) if start <= now < end else None
    return {
        "planet": key,
        "english": PLANETS[key][0],
        "sanskrit": PLANETS[key][1],
        "division": division,
        "year": year,
        "timezone": timezone_name,
        "startsIn": _division_label(initial, division)["name"],
        "current": _division_label(now_index, division)["name"] if now_index is not None else None,
        "entries": entries,
    }


# --- vakri and margi ------------------------------------------------------------


def _station(key: str, low: float, high: float) -> float:
    retro_at_low = _speed(key, low) < 0
    return _bisect(lambda t: (_speed(key, t) < 0) == retro_at_low, low, high)


def _sign_and_degree(longitude: float) -> str:
    sign = int(longitude // 30)
    degree = longitude - sign * 30
    whole = int(degree)
    minutes = int((degree - whole) * 60)
    return f"{whole:02d}° {SIGN_NAMES[sign]} {minutes:02d}′"


def retrogrades(key: str, timezone_name: str, year: int) -> dict:
    if key not in RETROGRADE_PLANETS:
        raise ValueError(f"'{key}' has no retrograde motion to list.")
    zone = _zone(timezone_name)
    _ephemeris_ready()
    start, end = _year_bounds(year, zone)

    # Look back far enough to catch a retrograde already under way on 1 January;
    # the slow grahas stay retrograde for up to five months.
    jd = start - 200
    stations: list[tuple[float, bool]] = []
    retro = _speed(key, jd) < 0
    while jd < end + 200:
        nxt = jd + 1.0
        now_retro = _speed(key, nxt) < 0
        if now_retro != retro:
            stations.append((_station(key, jd, nxt), now_retro))
            retro = now_retro
        jd = nxt

    periods = []
    for i, (when, becomes_retro) in enumerate(stations):
        if not becomes_retro or i + 1 >= len(stations):
            continue
        ends = stations[i + 1][0]
        # Kept when any part of it falls in the year.
        if ends < start or when >= end:
            continue
        periods.append(
            {
                "retrograde": _iso(when, zone),
                "direct": _iso(ends, zone),
                "retrogradeAt": _sign_and_degree(_longitude(key, when)),
                "directAt": _sign_and_degree(_longitude(key, ends)),
                "days": math.ceil(ends - when),
            }
        )
    return {
        "planet": key,
        "english": PLANETS[key][0],
        "sanskrit": PLANETS[key][1],
        "year": year,
        "timezone": timezone_name,
        "periods": periods,
        "totalDays": sum(p["days"] for p in periods),
    }


# --- asta and uday --------------------------------------------------------------


def _combust(key: str, jd: float) -> bool:
    english = PLANETS[key][0]
    longitude, _lat, speed = _position(key, jd)
    sun = _longitude("surya", jd)
    return is_combust(english, longitude, sun, speed < 0)


def combustions(key: str, timezone_name: str, year: int) -> dict:
    if key not in ASTA_PLANETS:
        raise ValueError(f"'{key}' has no classical combustion orb.")
    zone = _zone(timezone_name)
    _ephemeris_ready()
    start, end = _year_bounds(year, zone)
    step = 1 / 24 if key == "chandra" else 0.25

    jd = start - 120
    state = _combust(key, jd)
    edges: list[tuple[float, bool]] = []
    while jd < end + 120:
        nxt = jd + step
        now = _combust(key, nxt)
        if now != state:
            edges.append((_bisect(lambda t: _combust(key, t) == state, jd, nxt), now))
            state = now
        jd = nxt

    periods = []
    for i, (when, becomes_combust) in enumerate(edges):
        if not becomes_combust or i + 1 >= len(edges):
            continue
        ends = edges[i + 1][0]
        if ends < start or when >= end:
            continue
        periods.append(
            {
                "starts": _iso(when, zone),
                "ends": _iso(ends, zone),
                "startsAt": _sign_and_degree(_longitude(key, when)),
                "endsAt": _sign_and_degree(_longitude(key, ends)),
                "retrograde": _speed(key, (when + ends) / 2) < 0,
                "days": math.ceil(ends - when),
            }
        )
    english = PLANETS[key][0]
    return {
        "planet": key,
        "english": english,
        "sanskrit": PLANETS[key][1],
        "year": year,
        "timezone": timezone_name,
        "orb": COMBUSTION_ORBS[english],
        "orbRetrograde": COMBUSTION_ORBS_RETROGRADE.get(english),
        "periods": periods,
        "totalDays": sum(p["days"] for p in periods),
    }


# --- purnima and amavasya -------------------------------------------------------


def _elongation(jd: float) -> float:
    moon = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)[0][0]
    sun = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0]
    return (moon - sun) % 360


def _tithi(jd: float) -> int:
    return int(_elongation(jd) // 12)


def _sidereal_sun_sign(jd: float) -> int:
    return int(_longitude("surya", jd) // 30)


def _sunrise_on(day: date_type, latitude: float, longitude: float, zone) -> float:
    return _sun_event(_julian(datetime(day.year, day.month, day.day, tzinfo=zone)), latitude, longitude, True)


def _new_moons(start: float, end: float) -> list[float]:
    """Moments the elongation passes 0, covering the window with margin."""
    moons = []
    jd = start
    previous = _elongation(jd)
    while jd < end:
        nxt = jd + 0.25
        value = _elongation(nxt)
        if value < previous:
            moons.append(_bisect(lambda t: _elongation(t) > 180, jd, nxt))
        previous = value
        jd = nxt
    return moons


def _amanta_month(new_moon_before: float, new_moon_after: float) -> tuple[str, bool]:
    """The amanta month between two new moons, named for the sankranti it holds.

    With no sankranti between them the month is Adhika and takes the name of
    the month that follows.
    """
    sign_start = _sidereal_sun_sign(new_moon_before)
    sign_end = _sidereal_sun_sign(new_moon_after)
    # LUNAR_MONTHS is indexed by the Sun's sign at the opening new moon, with
    # Meena (11) giving Chaitra.
    if sign_start == sign_end:
        return LUNAR_MONTHS[sign_start], True
    return LUNAR_MONTHS[sign_start], False


def _sun_window(day: date_type, latitude: float, longitude: float, zone) -> tuple[float, float]:
    sunrise = _sunrise_on(day, latitude, longitude, zone)
    sunset = _sun_event(sunrise, latitude, longitude, False)
    return sunrise, sunset


def lunar_days(kind: str, latitude: float, longitude: float, timezone_name: str, year: int) -> dict:
    if kind not in ("purnima", "amavasya"):
        raise ValueError("kind must be 'purnima' or 'amavasya'.")
    zone = _zone(timezone_name)
    _ephemeris_ready()
    start, end = _year_bounds(year, zone)
    target = 14 if kind == "purnima" else 29

    new_moons = _new_moons(start - 70, end + 70)

    entries = []
    jd = start - 2
    inside = _tithi(jd) == target
    begin = None
    while jd < end + 2:
        nxt = jd + 0.25
        now_inside = _tithi(nxt) == target
        if now_inside and not inside:
            begin = _bisect(lambda t: _tithi(t) == target, jd, nxt)
        if inside and not now_inside and begin is not None:
            finish = _bisect(lambda t: _tithi(t) == target, jd, nxt)
            entries.extend(_observances(kind, begin, finish, new_moons, latitude, longitude, zone))
            begin = None
        inside = now_inside
        jd = nxt

    entries = [e for e in entries if e["date"].startswith(str(year))]
    entries.sort(key=lambda e: (e["date"], e["order"]))
    today = datetime.now(zone).date().isoformat()
    upcoming = next((e for e in entries if e["date"] >= today), None)
    return {
        "kind": kind,
        "year": year,
        "timezone": timezone_name,
        "entries": entries,
        "next": {"name": upcoming["names"][0], "date": upcoming["date"]} if upcoming else None,
        "note": (
            "Times are local to the selected place, adjusted for daylight saving where it "
            "applies. Times past midnight carry the next date. The Panchang day runs from "
            "one sunrise to the next."
        ),
    }


def _observances(kind, begin, finish, new_moons, latitude, longitude, zone) -> list[dict]:
    """The day or days a tithi window is kept on.

    The tithi day is the one whose sunrise falls inside the window (udaya tithi);
    a window holding no sunrise is kept on the day it starts. The Purnima vrat is
    the first day on which Purnima prevails at midday, which can be the day
    before, on Chaturdashi.
    """
    first_day = _moment(begin, zone).date()
    last_day = _moment(finish, zone).date()

    tithi_day = None
    vrat_day = None
    day = first_day
    while day <= last_day:
        sunrise, sunset = _sun_window(day, latitude, longitude, zone)
        if tithi_day is None and begin <= sunrise < finish:
            tithi_day = day
        midday = (sunrise + sunset) / 2
        if vrat_day is None and begin <= midday < finish:
            vrat_day = day
        day += timedelta(days=1)
    tithi_day = tithi_day or first_day

    # The amanta month holding this tithi lies between the new moons around it.
    middle = (begin + finish) / 2
    if kind == "amavasya":
        # The Amavasya tithi ends at the new moon that closes its amanta month.
        closing = min(new_moons, key=lambda nm: abs(nm - finish))
        opening = max(nm for nm in new_moons if nm < closing - 1)
    else:
        opening = max(nm for nm in new_moons if nm <= middle)
        closing = min(nm for nm in new_moons if nm > middle)
    month, adhika = _amanta_month(opening, closing)

    times = {"begins": _iso(begin, zone), "ends": _iso(finish, zone)}

    if kind == "purnima":
        label = f"{month} {'Adhika ' if adhika else ''}Purnima"
        paksha = f"{month}{' Adhika' if adhika else ''}, Shukla Purnima"
        if vrat_day and vrat_day != tithi_day:
            return [
                _entry(vrat_day, [f"{label} Vrat"], paksha, times, zone, order=0),
                _entry(tithi_day, [label], paksha, times, zone, order=1),
            ]
        return [_entry(tithi_day, [f"{label} Vrat", label], paksha, times, zone, order=0)]

    # North Indian (purnimanta) usage names the Amavasya for the month whose
    # dark half it ends, which is the amanta month that follows, except in an
    # Adhika month, which keeps its own name.
    if adhika:
        name = f"{month} Adhika Amavasya"
        paksha = f"{month} Adhika, Krishna Amavasya"
    else:
        following = LUNAR_MONTHS[(LUNAR_MONTHS.index(month) + 1) % 12]
        name = f"{following} Amavasya"
        paksha = f"{following}, Krishna Amavasya"
    names = ["Darsha Amavasya", name]
    weekday = tithi_day.weekday()
    if weekday == 0:
        names.append("Somvati Amavasya")
    elif weekday == 5:
        names.append("Shani Amavasya")
    return [_entry(tithi_day, names, paksha, times, zone, order=0)]


def _entry(day: date_type, names: list[str], paksha: str, times: dict, zone, order: int) -> dict:
    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "names": names,
        "paksha": paksha,
        "order": order,
        **times,
    }


# --- the positions table --------------------------------------------------------

_AYANAMSHAS = {
    "lahiri": swe.SIDM_LAHIRI,
    "raman": swe.SIDM_RAMAN,
    "kp": swe.SIDM_KRISHNAMURTI,
}
_TABLE_ORDER = ["surya", "chandra", "mangal", "budha", "guru", "shukra", "shani"]
_OUTER = ["arun", "varun", "yama"]


def _dms(value: float, positive: str = "N", negative: str = "S") -> str:
    hemisphere = positive if value >= 0 else negative
    value = abs(value)
    whole = int(value)
    minutes = int((value - whole) * 60)
    seconds = int(round(((value - whole) * 60 - minutes) * 60))
    if seconds == 60:
        minutes, seconds = minutes + 1, 0
    if minutes == 60:
        whole, minutes = whole + 1, 0
    return f"{whole:02d}° {hemisphere} {minutes:02d}′ {seconds:02d}″"


def _longitude_label(longitude: float) -> str:
    sign = int(longitude // 30)
    degree = longitude - sign * 30
    whole = int(degree)
    minutes_float = (degree - whole) * 60
    minutes = int(minutes_float)
    seconds = int((minutes_float - minutes) * 60)
    return f"{whole:02d}° {SIGN_NAMES[sign]} {minutes:02d}′ {seconds:02d}″"


def _row(name: str, english: str, longitude: float, latitude: float, speed: float,
         ra: float, dec: float, sidereal: bool, sun_longitude: float | None, kind: str) -> dict:
    index, _fraction = nakshatra_index_and_fraction(longitude)
    pada = min(int(_fraction * 4), 3) + 1
    lord = DASHA_SEQUENCE[index % len(DASHA_SEQUENCE)]
    sign_number = int(longitude // 30) + 1
    degree = longitude % 30
    retro = speed < 0 and kind != "lagna"
    combust = (
        sun_longitude is not None
        and english not in ("Sun", "Rahu", "Ketu")
        and kind == "graha"
        and is_combust(english, longitude, sun_longitude, retro)
    )
    classical = english in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
    return {
        "name": name,
        "english": english,
        "kind": kind,
        "longitude": _longitude_label(longitude),
        "sign": SIGN_NAMES[sign_number - 1],
        "fullDegree": round(longitude, 2),
        "nakshatra": NAKSHATRA_NAMES[index],
        "pada": pada,
        "nakshatraLord": NAKSHATRA_LORDS_SANSKRIT[lord],
        "subLord": NAKSHATRA_LORDS_SANSKRIT[sub_lord(longitude)],
        "latitude": _dms(latitude),
        "speed": round(speed, 2),
        "rightAscension": round(ra, 2),
        "declination": round(dec, 2),
        "retrograde": retro,
        "combust": combust,
        "motion": "Lagna" if kind == "lagna" else ("Retrograde" if retro else "Direct"),
        "dignity": planet_dignity(english, sign_number, degree) if classical and kind == "graha" else "",
        "relation": planet_relation(english, sign_number) if classical and kind == "graha" else "",
        "sidereal": sidereal,
    }


def positions(
    latitude: float,
    longitude: float,
    timezone_name: str,
    moment: datetime,
    ayanamsha: str = "lahiri",
    true_nodes: bool = False,
    outer: bool = True,
) -> dict:
    zone = _zone(timezone_name)
    if ayanamsha not in (*_AYANAMSHAS, "tropical"):
        raise ValueError("Unknown ayanamsha.")
    _ephemeris_ready()
    local = moment.replace(tzinfo=zone) if moment.tzinfo is None else moment.astimezone(zone)
    jd = _julian(local)

    sidereal = ayanamsha != "tropical"
    if sidereal:
        swe.set_sid_mode(_AYANAMSHAS[ayanamsha], 0, 0)
    side_flag = swe.FLG_SIDEREAL if sidereal else 0

    try:
        def calc(body: int) -> tuple:
            return swe.calc_ut(jd, body, _FLAGS | side_flag)[0]

        def equatorial(body: int) -> tuple:
            return swe.calc_ut(jd, body, _FLAGS | swe.FLG_EQUATORIAL)[0]

        sun_longitude = calc(swe.SUN)[0] % 360
        rows = []

        # Lagna, with its rate from a one-minute difference.
        def ascendant(t: float) -> float:
            return swe.houses_ex(t, latitude, longitude, b"P", side_flag)[1][0] % 360

        asc = ascendant(jd)
        asc_speed = ((ascendant(jd + 1 / 1440) - asc + 540) % 360 - 180) * 1440
        eps = swe.calc_ut(jd, swe.ECL_NUT)[0][0]
        ayan = swe.get_ayanamsa_ut(jd) if sidereal else 0.0
        asc_ra, asc_dec, _ = swe.cotrans(((asc + ayan) % 360, 0.0, 1.0), -eps)
        rows.append(_row("Lagna", "Ascendant", asc, 0.0, asc_speed, asc_ra, asc_dec, sidereal, None, "lagna"))

        order = _TABLE_ORDER + (_OUTER if outer else [])
        for key in order:
            english, sanskrit, body = PLANETS[key]
            lon, lat, _dist, speed = calc(body)[:4]
            ra, dec = equatorial(body)[:2]
            rows.append(_row(sanskrit, english, lon % 360, lat, speed, ra, dec, sidereal, sun_longitude, "graha"))

        node_bodies = [(swe.TRUE_NODE, "") ] if true_nodes else [(swe.MEAN_NODE, "")]
        # The other convention is listed after, as drik-style "Spashta" (true) rows.
        node_bodies.append((swe.MEAN_NODE, "Madhya ") if true_nodes else (swe.TRUE_NODE, "Spashta "))
        for body, prefix in node_bodies:
            lon, lat, _dist, speed = calc(body)[:4]
            ra, dec = equatorial(body)[:2]
            ketu_ra, ketu_dec, _ = swe.cotrans((((lon + 180) % 360 + ayan) % 360, 0.0, 1.0), -eps)
            kind = "graha" if not prefix else "node-alt"
            rows.append(_row(f"{prefix}Rahu", "Rahu", lon % 360, 0.0, speed, ra, dec, sidereal, sun_longitude, kind))
            rows.append(_row(f"{prefix}Ketu", "Ketu", (lon + 180) % 360, 0.0, speed, ketu_ra, ketu_dec, sidereal, sun_longitude, kind))

        ayanamsha_value = swe.get_ayanamsa_ut(jd) if sidereal else 0.0
    finally:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)

    return {
        "moment": local.replace(microsecond=0).isoformat(),
        "timezone": timezone_name,
        "ayanamsha": ayanamsha,
        "ayanamshaValue": _dms(ayanamsha_value).replace(" N ", " ").replace(" S ", " "),
        "trueNodes": true_nodes,
        "ascendantSign": int(asc // 30) + 1,
        "rows": rows,
    }


__all__ = [
    "PLANETS",
    "RETROGRADE_PLANETS",
    "ASTA_PLANETS",
    "transits",
    "retrogrades",
    "combustions",
    "lunar_days",
    "positions",
]
