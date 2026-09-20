from datetime import datetime, timedelta

from dateutil import tz

from app.services.panchang import compute_panchang

IST = tz.gettz("Asia/Kolkata")
JABALPUR = (23.170152, 79.932451, "Asia/Kolkata", "Jabalpur, India")


def jabalpur(moment: datetime):
    return compute_panchang(*JABALPUR, moment=moment)


def test_panchang_matches_a_published_reference() -> None:
    # drikpanchang.com for Jabalpur, 20 September 2026. Sunrise, sunset and the
    # nakshatra end time match to the minute; tithi/yoga/karana end times agree
    # within a minute, which is sub-arcsecond ayanamsha drift.
    result = jabalpur(datetime(2026, 9, 20, 15, 15, tzinfo=IST))

    assert result.sunrise.strftime("%I:%M %p") == "05:58 AM"
    assert result.sunset.strftime("%I:%M %p") == "06:09 PM"
    assert result.tithi.name == "Navami"
    assert result.paksha == "Shukla Paksha"
    assert result.nakshatra.name == "Purva Ashadha"
    assert result.nakshatra.ends_at.strftime("%I:%M %p %d %b") == "04:34 AM 21 Sep"
    assert result.yoga.name == "Saubhagya"
    assert [k.name for k in result.karanas] == ["Kaulava", "Taitila"]
    assert result.vara == "Raviwara"
    assert result.amanta_month == "Bhadrapada"
    assert result.purnimanta_month == "Bhadrapada"
    assert result.moonsign == "Dhanu"
    assert result.sunsign == "Kanya"
    assert result.shaka_samvat == "1948 Parabhava"
    assert result.vikram_samvat == "2083 Siddharthi"


def test_graha_positions_match_the_reference() -> None:
    result = jabalpur(datetime(2026, 9, 20, 15, 15, tzinfo=IST))
    by_name = {g.name: g for g in result.grahas}

    assert by_name["Moon"].sign == "Dhanu"
    assert by_name["Moon"].longitude == 260.04
    assert by_name["Moon"].motion == "Margi"
    assert by_name["Saturn"].sign == "Meena"
    assert by_name["Saturn"].motion == "Vakri"
    # Rahu and Ketu are always retrograde and exactly opposite.
    assert by_name["Ketu"].motion == "Vakri"
    assert abs((by_name["Rahu"].longitude - by_name["Ketu"].longitude) % 360 - 180) < 0.01


def test_vara_changes_at_sunrise_not_midnight() -> None:
    # 01:00 on Sunday is still Shaniwara, because the vara turns at sunrise.
    before = jabalpur(datetime(2026, 9, 20, 1, 0, tzinfo=IST))
    after = jabalpur(datetime(2026, 9, 20, 9, 0, tzinfo=IST))
    assert before.vara == "Shaniwara"
    assert after.vara == "Raviwara"


def test_vedic_clock_counts_ghatis_from_sunrise() -> None:
    result = jabalpur(datetime(2026, 9, 20, 15, 15, tzinfo=IST))
    # One ghati is 24 minutes, so a full day is 60 ghatis.
    elapsed_minutes = (result.moment - result.sunrise).total_seconds() / 60
    assert result.ghati == int(elapsed_minutes // 24)
    assert 0 <= result.pal < 60
    assert 0 <= result.vipal < 60


def test_a_different_place_gives_a_different_sunrise() -> None:
    # London on the same day: the panchang must follow the location given, not a
    # hardcoded default.
    london = compute_panchang(51.5072, -0.1276, "Europe/London", "London",
                              moment=datetime(2026, 9, 20, 12, 0, tzinfo=tz.gettz("Europe/London")))
    assert london.location == "London"
    assert london.timezone == "Europe/London"
    assert london.sunrise.tzinfo is not None
    assert london.sunrise.hour in (6, 7)


def test_timeline_bands_span_sunrise_to_sunrise() -> None:
    # The chart rows for the same reference day. Nakshatra matches drikpanchang
    # exactly; tithi and yoga sit a minute out, the same ayanamsha drift the
    # headline values carry.
    line = jabalpur(datetime(2026, 9, 20, 15, 15, tzinfo=IST)).timeline

    assert line.vara == "Raviwara"
    assert line.sunrise.strftime("%I:%M %p") == "05:58 AM"
    assert line.next_sunrise.date() == line.sunrise.date() + timedelta(days=1)

    for band in (line.tithi, line.nakshatra, line.yoga, line.karana):
        # Every row tiles the window end to end, with no gap or overlap.
        assert band[0].starts_at == line.sunrise
        assert band[-1].ends_at == line.next_sunrise
        for earlier, later in zip(band, band[1:]):
            assert earlier.ends_at == later.starts_at

    assert [(s.name, s.extra) for s in line.tithi] == [
        ("Navami", "Shukla"), ("Dashami", "Shukla")
    ]
    assert line.tithi[0].ends_at.strftime("%I:%M %p") == "05:52 PM"
    assert [s.name for s in line.nakshatra] == ["Purva Ashadha", "Uttara Ashadha"]
    assert line.nakshatra[0].ends_at.strftime("%I:%M %p %d %b") == "04:34 AM 21 Sep"
    assert [s.name for s in line.yoga] == ["Saubhagya", "Shobhana"]
    assert [s.name for s in line.karana] == ["Kaulava", "Taitila"]


def test_choghadiya_follows_the_classical_weekday_tables() -> None:
    line = jabalpur(datetime(2026, 9, 20, 15, 15, tzinfo=IST)).timeline
    day, night = line.choghadiya[:8], line.choghadiya[8:]

    # Sunday, the published sequences.
    assert [s.name for s in day] == [
        "Udvega", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga", "Udvega"
    ]
    assert [s.name for s in night] == [
        "Shubha", "Amrita", "Chara", "Roga", "Kala", "Labha", "Udvega", "Shubha"
    ]
    assert day[0].starts_at == line.sunrise
    assert day[-1].ends_at == line.sunset
    assert night[0].starts_at == line.sunset
    assert night[-1].ends_at == line.next_sunrise
    assert {s.name for s in line.choghadiya if s.extra == "Inauspicious"} == {
        "Udvega", "Kala", "Roga"
    }


def test_monday_choghadiya_starts_with_the_moon() -> None:
    # A second weekday, so the table is not just the Sunday special case.
    line = jabalpur(datetime(2026, 9, 21, 12, 0, tzinfo=IST)).timeline
    assert line.vara == "Somawara"
    assert [s.name for s in line.choghadiya[:8]] == [
        "Amrita", "Kala", "Shubha", "Roga", "Udvega", "Chara", "Labha", "Amrita"
    ]
    assert [s.name for s in line.choghadiya[8:]] == [
        "Chara", "Roga", "Kala", "Labha", "Udvega", "Shubha", "Amrita", "Chara"
    ]
