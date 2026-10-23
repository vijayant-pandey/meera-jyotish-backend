"""Equinoxes and solstices: the moment the Sun's tropical longitude reaches
0, 90, 180 or 270 degrees, with the day length around it at a place.

The crossing uses the apparent geocentric tropical longitude in Universal
Time, the definition almanacs publish. Sunrise and sunset come from the same
upper-limb, refracted definition the panchang uses, kept to the second here
because day lengths either side of a solstice differ by only seconds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import swisseph as swe
from dateutil import tz

from app.services.panchang import _ephemeris_ready, _sun_event

EVENTS = {
    "vernal-equinox": (0.0, "Vernal Equinox", "March Equinox"),
    "summer-solstice": (90.0, "Summer Solstice", "June Solstice"),
    "autumnal-equinox": (180.0, "Autumnal Equinox", "September Equinox"),
    "winter-solstice": (270.0, "Winter Solstice", "December Solstice"),
}


def _moment(jd: float, zone) -> datetime:
    year, month, day, hours = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=hours)
    return base.astimezone(zone).replace(microsecond=0)


def _julian(moment: datetime) -> float:
    utc = moment.astimezone(timezone.utc)
    hours = utc.hour + utc.minute / 60 + utc.second / 3600
    return swe.julday(utc.year, utc.month, utc.day, hours, swe.GREG_CAL)


def _crossing(longitude: float, year: int) -> float:
    return swe.solcross_ut(longitude, swe.julday(year, 1, 1, 0.0, swe.GREG_CAL), swe.FLG_SWIEPH)


def _duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d} Hours {minutes:02d} Mins {secs:02d} Secs"


def _day(latitude: float, longitude: float, zone, on) -> dict:
    midnight = datetime(on.year, on.month, on.day, tzinfo=zone)
    sunrise = _sun_event(_julian(midnight), latitude, longitude, rising=True)
    sunset = _sun_event(sunrise, latitude, longitude, rising=False)
    return {
        "sunrise": _moment(sunrise, zone).isoformat(),
        "sunset": _moment(sunset, zone).isoformat(),
        "seconds": (sunset - sunrise) * 86400,
    }


def season(event: str, latitude: float, longitude: float, timezone_name: str, year: int, label: str) -> dict:
    if event not in EVENTS:
        raise ValueError(f"Unknown event '{event}'.")
    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")
    _ephemeris_ready()

    target, title, alias = EVENTS[event]
    moment = _moment(_crossing(target, year), zone)
    on = moment.date()

    today = _day(latitude, longitude, zone, on)
    before = _day(latitude, longitude, zone, on - timedelta(days=1))
    after = _day(latitude, longitude, zone, on + timedelta(days=1))

    others = []
    for key, (degrees, name, _alias) in EVENTS.items():
        when = _moment(_crossing(degrees, year), zone)
        others.append({"event": key, "title": name, "moment": when.isoformat()})

    return {
        "event": event,
        "title": title,
        "alias": alias,
        "year": year,
        "location": label,
        "timezone": timezone_name,
        "moment": moment.isoformat(),
        "date": on.isoformat(),
        "weekday": moment.strftime("%A"),
        "sunrise": today["sunrise"],
        "sunset": today["sunset"],
        "dayDuration": _duration(today["seconds"]),
        "previousDayDuration": _duration(before["seconds"]),
        "nextDayDuration": _duration(after["seconds"]),
        "nightDuration": _duration(86400 - today["seconds"]),
        "seasons": others,
        "note": (
            "All times are local to the selected place, adjusted for daylight saving where it "
            "applies. Times past midnight belong to the next calendar date. The Panchang day "
            "runs from one sunrise to the next."
        ),
    }


__all__ = ["EVENTS", "season"]
