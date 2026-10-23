from datetime import datetime

from app.services import planet_events as pe

ZONE = "Asia/Kolkata"
DELHI = (28.6356, 77.2244)


def test_mercury_retrogrades_of_2026() -> None:
    data = pe.retrogrades("budha", ZONE, 2026)
    stations = [(p["retrograde"][:16], p["direct"][:16]) for p in data["periods"]]
    assert stations[0] == ("2026-02-26T12:17", "2026-03-21T01:02")
    assert [p["days"] for p in data["periods"]] == [23, 25, 21]
    assert data["totalDays"] == 69


def test_purnima_vrat_falls_a_day_early_when_purnima_starts_before_midday() -> None:
    data = pe.lunar_days("purnima", *DELHI, ZONE, 2026)
    by_date = {e["date"]: e for e in data["entries"]}
    assert by_date["2026-01-03"]["names"] == ["Pausha Purnima Vrat", "Pausha Purnima"]
    assert by_date["2026-01-03"]["begins"].startswith("2026-01-02T18:53")
    assert by_date["2026-10-25"]["names"] == ["Ashwina Purnima Vrat"]
    assert by_date["2026-10-26"]["names"] == ["Ashwina Purnima"]
    assert by_date["2026-05-31"]["names"] == ["Jyeshtha Adhika Purnima"]


def test_amavasya_names_follow_purnimanta_months() -> None:
    data = pe.lunar_days("amavasya", *DELHI, ZONE, 2026)
    by_date = {e["date"]: e for e in data["entries"]}
    assert "Magha Amavasya" in by_date["2026-01-18"]["names"]
    assert "Shani Amavasya" in by_date["2026-05-16"]["names"]
    assert "Jyeshtha Adhika Amavasya" in by_date["2026-06-15"]["names"]
    assert "Somvati Amavasya" in by_date["2026-06-15"]["names"]


def test_mars_rashi_transits_of_2026() -> None:
    data = pe.transits("mangal", "rashi", ZONE, 2026)
    names = [e["name"] for e in data["entries"]]
    assert names[:2] == ["Makara", "Kumbha"]
    assert data["entries"][0]["time"].startswith("2026-01-16")


def test_sun_passes_through_all_108_padas() -> None:
    assert len(pe.transits("surya", "pada", ZONE, 2026)["entries"]) == 108


def test_positions_table_marks_retrograde_and_nodes() -> None:
    data = pe.positions(*DELHI, ZONE, datetime(2026, 10, 19, 0, 58, 46))
    rows = {r["name"]: r for r in data["rows"]}
    assert rows["Surya"]["nakshatra"] == "Chitra" and rows["Surya"]["pada"] == 3
    assert rows["Shukra"]["retrograde"] and rows["Shani"]["retrograde"]
    assert rows["Rahu"]["sign"] == "Kumbha" and rows["Ketu"]["sign"] == "Simha"
    assert "Spashta Rahu" in rows
