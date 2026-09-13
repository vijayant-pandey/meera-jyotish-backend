from datetime import date

import pytest

from app.schemas import Meridiem
from app.services.time_utils import parse_12h_time, resolve_birth_datetimes


def test_parse_12h_time_handles_midnight() -> None:
    result = parse_12h_time("12:05", Meridiem.am)
    assert result.hour == 0
    assert result.minute == 5


def test_parse_12h_time_handles_afternoon() -> None:
    result = parse_12h_time("1:45", Meridiem.pm)
    assert result.hour == 13
    assert result.minute == 45


def test_resolve_birth_datetimes_rejects_dst_gap() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        resolve_birth_datetimes(
            date(2024, 3, 10),
            "02:15",
            Meridiem.am,
            "America/New_York",
        )

