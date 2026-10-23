import pytest

from app.services.seasons import season

DELHI = (28.6356, 77.2244, "Asia/Kolkata")


@pytest.mark.parametrize(
    "event, expected",
    [
        # Published UT instants converted to IST: 14:46, 08:24, 00:05, 20:50 UT.
        ("vernal-equinox", "2026-03-20T20:1"),
        ("summer-solstice", "2026-06-21T13:5"),
        ("autumnal-equinox", "2026-09-23T05:3"),
        ("winter-solstice", "2026-12-22T02:2"),
    ],
)
def test_crossings_land_on_the_published_minute(event: str, expected: str) -> None:
    lat, lng, zone = DELHI
    assert season(event, lat, lng, zone, 2026, "New Delhi")["moment"].startswith(expected)


def test_winter_solstice_day_lengths_barely_change() -> None:
    lat, lng, zone = DELHI
    data = season("winter-solstice", lat, lng, zone, 2026, "New Delhi")
    assert data["date"] == "2026-12-22"
    assert data["sunrise"].startswith("2026-12-22T07:09")
    assert data["sunset"].startswith("2026-12-22T17:29")
    assert data["dayDuration"].startswith("10 Hours 19 Mins")
    assert data["previousDayDuration"].startswith("10 Hours 19 Mins")
    assert data["nextDayDuration"].startswith("10 Hours 19 Mins")
