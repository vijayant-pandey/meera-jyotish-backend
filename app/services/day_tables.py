"""Day tables: choghadiya and hora, for the dedicated muhurta pages.

The generic almanac sections return flat columns/rows. These pages need more
than a table: day and night side by side, each slot's quality word, which slot
is running now, and which slots overlap Rahu Kala. Both share one shape so a
single layout renders either.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta

# Order of the eight slots, and the quality word published beside each name.
CHOGHADIYA_ORDER = ["Udvega", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga"]
QUALITY = {
    "Udvega": "Bad",
    "Chara": "Neutral",
    "Labha": "Gain",
    "Amrita": "Best",
    "Kala": "Loss",
    "Shubha": "Good",
    "Roga": "Evil",
}
TONE = {
    "Amrita": "good",
    "Shubha": "good",
    "Labha": "good",
    "Chara": "neutral",
    "Udvega": "bad",
    "Kala": "bad",
    "Roga": "bad",
}


def _sun_times(latitude: float, longitude: float, timezone_name: str, on: date_type):
    from dateutil import tz

    from app.services.panchang import _from_julian, _julian, _sun_event

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
        zone,
    )


def _rahu_window(sunrise: datetime, sunset: datetime) -> tuple[datetime, datetime]:
    """Rahu Kala is the nth eighth of the daylight span, by weekday.

    Counted from Sunday, the classical sequence of eighths is
    8th, 2nd, 7th, 5th, 6th, 4th, 3rd.
    """
    eighth = (sunset - sunrise) / 8
    sunday_first = (sunrise.weekday() + 1) % 7
    index = [7, 1, 6, 4, 5, 3, 2][sunday_first]
    return sunrise + eighth * index, sunrise + eighth * (index + 1)


def _slot(
    name: str,
    begins: datetime,
    ends: datetime,
    day_label: date_type,
    rahu: tuple[datetime, datetime],
) -> dict:
    # A slot that runs past midnight is labelled with the date it ends on,
    # which is how printed panchangs show it.
    crosses = ends.date() != day_label
    return {
        "name": name,
        # Callers that are not choghadiya overwrite these two.
        "quality": QUALITY.get(name, ""),
        "tone": TONE.get(name, "neutral"),
        "start": begins.isoformat(),
        "end": ends.isoformat(),
        "startLabel": begins.strftime("%I:%M %p").lstrip("0"),
        "endLabel": ends.strftime("%I:%M %p").lstrip("0")
        + (ends.strftime(", %b %d") if crosses else ""),
        # Rahu Kala sits inside the daylight span and overlaps exactly one slot.
        "rahuKala": begins < rahu[1] and ends > rahu[0],
    }


def detailed_choghadiya(
    latitude: float, longitude: float, timezone_name: str, on: date_type, label: str = ""
) -> dict:
    sunrise, sunset, next_sunrise, zone = _sun_times(latitude, longitude, timezone_name, on)
    rahu = _rahu_window(sunrise, sunset)
    sunday_first = (sunrise.weekday() + 1) % 7

    day: list[dict] = []
    night: list[dict] = []
    for bucket, begins, ends, first, step in (
        (day, sunrise, sunset, sunday_first * 3, 1),
        (night, sunset, next_sunrise, (sunday_first + 4) * 3, -2),
    ):
        width = (ends - begins) / 8
        for unit in range(8):
            name = CHOGHADIYA_ORDER[(first + step * unit) % 7]
            bucket.append(
                _slot(name, begins + width * unit, begins + width * (unit + 1), on, rahu)
            )

    return {
        "location": label or f"{latitude:.4f}, {longitude:.4f}",
        "timezone": timezone_name,
        "date": on.isoformat(),
        "weekday": sunrise.strftime("%A"),
        "dateLabel": sunrise.strftime("%B %d, %Y, %A").replace(" 0", " "),
        "sunrise": sunrise.isoformat(),
        "sunset": sunset.isoformat(),
        "nextSunrise": next_sunrise.isoformat(),
        "sunriseLabel": sunrise.strftime("%I:%M %p").lstrip("0"),
        "sunsetLabel": sunset.strftime("%I:%M %p").lstrip("0"),
        "rahuKalaStart": rahu[0].isoformat(),
        "rahuKalaEnd": rahu[1].isoformat(),
        "day": day,
        "night": night,
        "note": (
            "All timings are in 12-hour notation in the local time of this place, "
            "with DST applied where it is in force. Slots past midnight carry the "
            "next day's date. In panchang reckoning the day begins and ends at sunrise."
        ),
    }


# --- hora ---------------------------------------------------------------------

# Chaldean descending order. The first hora of a day belongs to that weekday's
# lord, and the sequence then steps through this list.
HORA_SEQUENCE = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]
WEEKDAY_LORDS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
HORA_QUALITY = {
    "Sun": "Vigorous",
    "Moon": "Gentle",
    "Mars": "Aggressive",
    "Mercury": "Quick",
    "Jupiter": "Fruitful",
    "Venus": "Beneficial",
    "Saturn": "Sluggish",
}


def detailed_hora(
    latitude: float, longitude: float, timezone_name: str, on: date_type, label: str = ""
) -> dict:
    """Twelve horas across the daylight and twelve across the night.

    Each side divides its own span, so a hora is near an hour but not exactly
    one. Tones are the classical graha colours rather than good/bad, because a
    hora is read by its lord, not by an auspicious verdict.
    """
    sunrise, sunset, next_sunrise, _zone = _sun_times(latitude, longitude, timezone_name, on)
    rahu = _rahu_window(sunrise, sunset)
    sunday_first = (sunrise.weekday() + 1) % 7
    cursor = HORA_SEQUENCE.index(WEEKDAY_LORDS[sunday_first])

    day: list[dict] = []
    night: list[dict] = []
    for bucket, begins, ends in ((day, sunrise, sunset), (night, sunset, next_sunrise)):
        width = (ends - begins) / 12
        for unit in range(12):
            lord = HORA_SEQUENCE[cursor % 7]
            cursor += 1
            slot = _slot(lord, begins + width * unit, begins + width * (unit + 1), on, rahu)
            slot["quality"] = HORA_QUALITY[lord]
            slot["tone"] = lord.lower()
            bucket.append(slot)

    return {
        "location": label or f"{latitude:.4f}, {longitude:.4f}",
        "timezone": timezone_name,
        "date": on.isoformat(),
        "weekday": sunrise.strftime("%A"),
        "dateLabel": sunrise.strftime("%B %d, %Y, %A").replace(" 0", " "),
        "sunrise": sunrise.isoformat(),
        "sunset": sunset.isoformat(),
        "nextSunrise": next_sunrise.isoformat(),
        "sunriseLabel": sunrise.strftime("%I:%M %p").lstrip("0"),
        "sunsetLabel": sunset.strftime("%I:%M %p").lstrip("0"),
        "rahuKalaStart": rahu[0].isoformat(),
        "rahuKalaEnd": rahu[1].isoformat(),
        "day": day,
        "night": night,
        "note": (
            "All timings are in 12-hour notation in the local time of this place, "
            "with DST applied where it is in force. Hours past midnight carry the "
            "next day's date. In panchang reckoning the day begins and ends at sunrise."
        ),
    }


# --- rahu kaal ----------------------------------------------------------------

# Which eighth of the daylight Rahu Kaal occupies, indexed from Sunday. This is
# the published rule: Monday the 2nd period, Saturday the 3rd, Friday the 4th,
# Wednesday the 5th, Thursday the 6th, Tuesday the 7th and Sunday the 8th. The
# first period after sunrise is never Rahu's on any weekday.
RAHU_PERIOD_BY_WEEKDAY = {
    "Sunday": 8,
    "Monday": 2,
    "Tuesday": 7,
    "Wednesday": 5,
    "Thursday": 6,
    "Friday": 4,
    "Saturday": 3,
}
_WEEKDAY_ORDER = [
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
]


def rahu_kaal(
    latitude: float, longitude: float, timezone_name: str, on: date_type, label: str = ""
) -> dict:
    sunrise, sunset, _next_sunrise, _zone = _sun_times(latitude, longitude, timezone_name, on)
    weekday = sunrise.strftime("%A")
    period = RAHU_PERIOD_BY_WEEKDAY[weekday]
    eighth = (sunset - sunrise) / 8
    begins = sunrise + eighth * (period - 1)
    ends = begins + eighth

    minutes = int(round((ends - begins).total_seconds() / 60))
    hours, rest = divmod(minutes, 60)
    duration = (
        f"{hours:02d} Hour{'s' if hours != 1 else ''} {rest:02d} Mins"
        if hours
        else f"{rest} Mins"
    )

    return {
        "location": label or f"{latitude:.4f}, {longitude:.4f}",
        "timezone": timezone_name,
        "date": on.isoformat(),
        "weekday": weekday,
        "dateLabel": sunrise.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "sunrise": sunrise.isoformat(),
        "sunset": sunset.isoformat(),
        "sunriseLabel": sunrise.strftime("%I:%M %p").lstrip("0"),
        "sunsetLabel": sunset.strftime("%I:%M %p").lstrip("0"),
        "start": begins.isoformat(),
        "end": ends.isoformat(),
        "startLabel": begins.strftime("%I:%M %p").lstrip("0"),
        "endLabel": ends.strftime("%I:%M %p").lstrip("0"),
        "durationLabel": duration,
        "period": period,
        # One entry per eighth, naming the weekday whose Rahu Kaal lands there.
        # The first is deliberately empty: no weekday puts Rahu in period one.
        "weekdayWheel": [
            {
                "period": index,
                "weekday": next(
                    (w for w in _WEEKDAY_ORDER if RAHU_PERIOD_BY_WEEKDAY[w] == index), ""
                ),
            }
            for index in range(1, 9)
        ],
        "note": (
            "All timings are in 12-hour notation in the local time of this place, "
            "with DST applied where it is in force. In panchang reckoning the day "
            "begins and ends at sunrise."
        ),
    }
