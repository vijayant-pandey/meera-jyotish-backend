import pytest

from app.services.eclipses import eclipses_for_year

DELHI = (28.6139, 77.209, "Asia/Kolkata")


def _year(kind: str, year: int) -> dict:
    lat, lng, zone = DELHI
    return eclipses_for_year(kind, lat, lng, zone, year, "New Delhi, India")


def _contact(eclipse: dict, label: str) -> str:
    return next(c["time"] for c in eclipse["contacts"] if c["label"] == label)


def test_total_lunar_eclipse_of_september_2025_matches_published_timings() -> None:
    eclipse = next(e for e in _year("lunar", 2025)["eclipses"] if e["date"] == "2025-09-07")
    assert eclipse["globalType"] == "Total"
    assert eclipse["visible"] is True
    assert _contact(eclipse, "First Contact with Umbra").startswith("2025-09-07T21:57")
    assert _contact(eclipse, "Last Contact with Umbra").startswith("2025-09-08T01:26")
    # Sutak starts nine hours before the umbral phase and ends with it.
    assert eclipse["sutak"]["begins"].startswith("2025-09-07T12:57")
    assert eclipse["sutak"]["ends"].startswith("2025-09-08T01:26")


def test_penumbral_lunar_eclipse_carries_no_sutak() -> None:
    eclipse = next(e for e in _year("lunar", 2027)["eclipses"] if e["date"] == "2027-02-21")
    assert eclipse["globalType"] == "Penumbral"
    assert eclipse["sutak"] is None
    assert _contact(eclipse, "Maximum Eclipse").startswith("2027-02-21T04:4")
    magnitude = float(eclipse["magnitudes"][0]["value"])
    assert magnitude == pytest.approx(0.92, abs=0.02)


def test_solar_eclipse_not_seen_from_india_has_no_local_timings() -> None:
    eclipse = next(e for e in _year("solar", 2026)["eclipses"] if e["date"] == "2026-08-12")
    assert eclipse["visible"] is False
    assert eclipse["contacts"] == []
    assert eclipse["sutak"] is None


def test_partial_solar_eclipse_of_august_2027_is_visible_from_delhi() -> None:
    data = _year("solar", 2027)
    eclipse = next(e for e in data["eclipses"] if e["date"] == "2027-08-02")
    assert eclipse["globalType"] == "Total"
    assert eclipse["localType"] == "Partial"
    assert eclipse["sutak"] is not None
    assert data["previous"] == "2026-08-12"
