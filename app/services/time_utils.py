from __future__ import annotations

from datetime import UTC, date, datetime, time

from dateutil import tz

from app.schemas import Meridiem


def parse_12h_time(value: str, meridiem: Meridiem) -> time:
    try:
        hour_text, minute_text = value.strip().split(":")
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Birth time must be in HH:MM format.") from exc

    if hour < 1 or hour > 12:
        raise ValueError("Hour must be between 1 and 12.")
    if minute < 0 or minute > 59:
        raise ValueError("Minute must be between 00 and 59.")

    if meridiem is Meridiem.am:
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12

    return time(hour=hour, minute=minute)


def resolve_birth_datetimes(
    birth_date: date,
    birth_time12h: str,
    meridiem: Meridiem,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")

    parsed_time = parse_12h_time(birth_time12h, meridiem)
    naive = datetime.combine(birth_date, parsed_time)
    local_dt = naive.replace(tzinfo=zone)

    if not tz.datetime_exists(local_dt):
        raise ValueError("Birth time does not exist in the selected timezone because of DST.")
    if tz.datetime_ambiguous(local_dt):
        raise ValueError(
            "Birth time is ambiguous in the selected timezone because of DST. "
            "Please adjust the time or timezone manually."
        )

    return local_dt, local_dt.astimezone(UTC)


def utc_decimal_hour(utc_dt: datetime) -> float:
    return (
        utc_dt.hour
        + utc_dt.minute / 60
        + utc_dt.second / 3600
        + utc_dt.microsecond / 3_600_000_000
    )
