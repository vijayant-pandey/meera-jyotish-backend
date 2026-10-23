from datetime import date, datetime, timedelta, timezone

import pytest

from app.schemas import (
    Ayanamsha,
    Gender,
    KundaliRequest,
    Meridiem,
    Precision,
    ResolvedPlace,
    Source,
)
from app.services.astrology import (
    _find_active_period,
    calculate_kundali,
    houses_ruled,
    is_combust,
    planet_dignity,
    planet_relation,
    sub_lord,
    nakshatra_index_and_fraction,
    nakshatra_info,
    vimshottari_dasha,
)


def build_payload(gender: Gender = Gender.other) -> KundaliRequest:
    return KundaliRequest(
        name="Ada Lovelace",
        gender=gender,
        birth_date=date(1815, 12, 10),
        birth_time12h="1:30",
        meridiem=Meridiem.pm,
        ayanamsha=Ayanamsha.lahiri,
        place=ResolvedPlace(
            label="London, United Kingdom",
            lat=51.507222,
            lng=-0.1275,
            timezone="Europe/London",
            country_code="GB",
            country="United Kingdom",
            admin="England",
            precision=Precision.city,
            source=Source.manual,
        ),
    )


def test_calculate_kundali_returns_north_india_chart() -> None:
    result = calculate_kundali(build_payload())
    assert result.chart.style == "north-india"
    assert len(result.chart.houses) == 12
    assert len(result.planets) == 9
    assert result.dasha.system == "Vimshottari"
    assert result.dasha.year_days == 365.25
    assert len(result.dasha.periods) == 9
    assert len(result.divisional_charts) == 21


def test_calculate_kundali_returns_planet_positions() -> None:
    result = calculate_kundali(build_payload())
    moon = next(planet for planet in result.planets if planet.name == "Moon")
    assert 1 <= moon.sign_number <= 12
    assert moon.nakshatra.name
    assert 1 <= moon.house_number <= 12


def test_calculate_kundali_returns_nested_dasha_path() -> None:
    result = calculate_kundali(build_payload())
    active = result.dasha.active_at_birth

    assert active.mahadasha_period.level.value == "mahadasha"
    assert active.antardasha_period.level.value == "antardasha"
    assert active.pratyantardasha_period.level.value == "pratyantardasha"
    assert active.sookshma_period.level.value == "sookshma"
    assert active.prana_period.level.value == "prana"
    assert active.deha_period is not None
    assert active.deha_period.level.value == "deha"

    assert active.mahadasha_period.start <= active.antardasha_period.start
    assert active.antardasha_period.start <= active.pratyantardasha_period.start
    assert active.pratyantardasha_period.start <= active.sookshma_period.start
    assert active.sookshma_period.start <= active.prana_period.start
    assert active.prana_period.start <= active.deha_period.start
    assert active.prana_period.end <= active.sookshma_period.end
    assert active.deha_period.end <= active.prana_period.end


def test_balance_at_birth_matches_remaining_fraction() -> None:
    result = calculate_kundali(build_payload())
    balance = result.dasha.balance_at_birth

    assert 0 < balance.remaining_nakshatra_fraction <= 1
    assert balance.remaining_days > 0
    assert balance.remaining_years > 0
    assert balance.start < balance.end


def test_vimshottari_periods_use_one_consistent_julian_year_basis() -> None:
    result = calculate_kundali(build_payload())
    dasha = result.dasha
    first_period = dasha.periods[0]

    # Derive the expected span from the lord the Moon actually starts on, so the test
    # stays correct if the fixture's birth details ever change.
    first_period_years = dasha.years_by_lord[first_period.lord]
    assert (first_period.end - first_period.start).total_seconds() == first_period_years * 365.25 * 86400
    assert (dasha.periods[-1].end - dasha.periods[0].start).total_seconds() == 120 * 365.25 * 86400


def test_calculate_kundali_returns_requested_divisional_charts() -> None:
    result = calculate_kundali(build_payload())
    keys = {entry.key for entry in result.divisional_charts}

    assert {"D1", "CHALIT", "D9", "D10", "D24", "D60"} <= keys
    chalit = next(entry for entry in result.divisional_charts if entry.key == "CHALIT")
    assert chalit.title == "Bhava Chalit"
    assert len(chalit.chart.houses) == 12
    navamsa = next(entry for entry in result.divisional_charts if entry.key == "D9")
    assert navamsa.chart.style == "north-india"
    assert len(navamsa.chart.houses) == 12


def test_moon_longitude_is_pinned_to_the_swiss_ephemeris() -> None:
    # Guards two regressions at once: silently falling back to the Moshier
    # ephemeris when the .se1 files go missing, and any loss of precision on the
    # way into the dasha. The dasha amplifies Moon error by ~274 days per degree.
    result = calculate_kundali(build_payload())
    moon = next(planet for planet in result.planets if planet.name == "Moon")

    assert moon.longitude == pytest.approx(344.6346, abs=5e-4)
    assert moon.nakshatra.name == "Uttara Bhadrapada"
    assert moon.nakshatra.pada == 4
    assert moon.nakshatra.lord == "Saturn"


def test_dasha_timeline_is_pinned_to_an_exact_instant() -> None:
    # The structural tests cannot catch a timeline that is shifted wholesale, so
    # pin a real timestamp. Without this, rounding the Moon before the dasha moved
    # every boundary by ~15 minutes undetected.
    result = calculate_kundali(build_payload())

    assert result.dasha.balance_at_birth.remaining_years == pytest.approx(2.895684, abs=1e-5)
    assert result.dasha.periods[0].start == datetime(
        1799, 11, 1, 11, 5, 21, 167913, tzinfo=timezone.utc
    )


def test_nakshatra_boundaries_are_exact() -> None:
    # Only every third boundary is a whole number of degrees (0, 40, 80 ... 320) and
    # therefore exactly representable as a float. Those are the ones the old
    # `// (360 / 27)` split pushed into the previous nakshatra. The remaining
    # boundaries are non-terminating, so no float sits exactly on them.
    for index in range(0, 27, 3):
        boundary = index * 40 / 3
        assert boundary == int(boundary)
        assert nakshatra_index_and_fraction(boundary)[0] == index
        assert nakshatra_index_and_fraction(boundary)[1] == pytest.approx(0.0, abs=1e-12)

    # Every nakshatra is still reachable from inside its own span.
    for index in range(27):
        midpoint = (index + 0.5) * 360 / 27
        assert nakshatra_index_and_fraction(midpoint)[0] == index

    assert nakshatra_info(40.0).name == "Rohini"
    assert nakshatra_info(40.0).lord == "Moon"
    assert nakshatra_info(40.0).pada == 1


def test_dasha_balance_is_full_at_a_nakshatra_boundary() -> None:
    # A Moon exactly on a boundary has traversed none of the nakshatra, so the
    # whole mahadasha remains. This previously reported the wrong lord with a
    # zero balance.
    dasha = vimshottari_dasha(40.0, datetime(1990, 12, 2, 7, 20, tzinfo=timezone.utc))

    assert dasha.balance_at_birth.lord == "Moon"
    assert dasha.balance_at_birth.remaining_years == pytest.approx(10.0)


def test_find_active_period_clamps_to_the_correct_end() -> None:
    # A moment before the timeline starts belongs to the first period. This used to
    # return the last period for anything out of range, in either direction.
    result = calculate_kundali(build_payload())
    periods = result.dasha.periods

    assert _find_active_period(periods, periods[0].start - timedelta(days=1)) is periods[0]
    assert _find_active_period(periods, periods[-1].end + timedelta(days=1)) is periods[-1]


def test_planet_dignity_matches_classical_tables() -> None:
    assert planet_dignity("Moon", 2, 2.0) == "Exalted"
    assert planet_dignity("Moon", 8, 10.0) == "Debilitated"
    assert planet_dignity("Jupiter", 4, 19.0) == "Exalted"
    assert planet_relation("Sun", 5) == "Own House"
    assert planet_relation("Sun", 8) == "Friend's House"
    assert planet_relation("Mars", 2) == "Neutral"
    assert planet_relation("Saturn", 5) == "Enemy's House"


def test_combustion_uses_the_tighter_retrograde_orb() -> None:
    # Venus is combust within 10 degrees when direct but only 8 when retrograde.
    assert is_combust("Venus", 100.0, 109.0, retrograde=False) is True
    assert is_combust("Venus", 100.0, 109.0, retrograde=True) is False
    # Separation is measured the short way around the zodiac.
    assert is_combust("Venus", 2.0, 355.0, retrograde=False) is True
    assert is_combust("Sun", 100.0, 100.0, retrograde=False) is False


def test_ascendant_is_exposed_with_its_nakshatra() -> None:
    result = calculate_kundali(build_payload())

    assert result.ascendant is not None
    assert result.ascendant.sign_name == result.chart.ascendant_sign_name
    assert 0 <= result.ascendant.degree_in_sign < 30
    assert 1 <= result.ascendant.nakshatra.pada <= 4


def test_kp_sub_lord_divides_the_nakshatra_in_vimshottari_proportion() -> None:
    # Checked against a published KP table: Lagna at 324.3231 (Purva Bhadrapada,
    # lord Jupiter) falls in the Mercury sub; Sun at 226.1108 (Anuradha, lord
    # Saturn) falls in the Jupiter sub.
    assert sub_lord(324.3231) == "Mercury"
    assert sub_lord(226.1108) == "Jupiter"
    # The first sub of any nakshatra is its own lord.
    assert sub_lord(0.01) == "Ketu"
    assert sub_lord(40.01) == "Moon"


def test_dignity_prefers_mooltrikona_over_exaltation() -> None:
    # The Moon exalts at 3 deg Taurus but its mooltrikona runs 4-30 deg, so a Moon
    # at 15 deg Taurus is reported as Mooltrikona rather than Exalted.
    assert planet_dignity("Moon", 2, 15.8) == "Mooltrikona"
    assert planet_dignity("Moon", 2, 2.0) == "Exalted"
    # Jupiter's mooltrikona is in Sagittarius, so in Cancer it stays Exalted.
    assert planet_dignity("Jupiter", 4, 19.85) == "Exalted"
    assert planet_dignity("Jupiter", 10, 5.0) == "Debilitated"
    assert planet_dignity("Mars", 8, 5.0) == "Own Sign"
    assert planet_dignity("Rahu", 10, 5.0) == ""


def test_relationship_is_about_the_sign_lord_not_dignity() -> None:
    assert planet_relation("Sun", 8) == "Friend's House"
    assert planet_relation("Moon", 2) == "Neutral"
    assert planet_relation("Sun", 5) == "Own House"
    # The nodes own no sign classically but still get a relationship.
    assert planet_relation("Ketu", 4) == "Enemy's House"
    assert planet_relation("Rahu", 10) == "Friend's House"


def test_houses_ruled_counts_from_the_ascendant() -> None:
    assert houses_ruled("Sun", 11) == [7]
    assert houses_ruled("Mars", 11) == [3, 10]
    # Modern co-rulership so the column is not blank for the nodes.
    assert houses_ruled("Rahu", 11) == [1]
    assert houses_ruled("Ketu", 11) == [10]


def test_gender_selects_the_kalatra_karaka() -> None:
    # Shukra signifies the wife in a male chart, Guru the husband in a female one.
    male = calculate_kundali(build_payload(gender=Gender.male))
    female = calculate_kundali(build_payload(gender=Gender.female))
    unstated = calculate_kundali(build_payload(gender=Gender.other))

    assert male.gender_context.spouse_karaka == "Venus"
    assert male.gender_context.spouse_karaka_sanskrit == "Shukra"
    assert female.gender_context.spouse_karaka == "Jupiter"
    assert female.gender_context.spouse_karaka_sanskrit == "Guru"
    # Not asserted when the gender is not stated, rather than guessed.
    assert unstated.gender_context.spouse_karaka == ""


def test_gender_changes_nothing_astronomical() -> None:
    # The whole point: positions, vargas, dasha and panchang are astronomy and
    # must be byte-identical whatever the gender. If this ever fails, a gender
    # dependency has been introduced somewhere it does not belong.
    male = calculate_kundali(build_payload(gender=Gender.male))
    female = calculate_kundali(build_payload(gender=Gender.female))

    assert male.planets == female.planets
    assert male.ascendant == female.ascendant
    assert male.chart == female.chart
    assert male.divisional_charts == female.divisional_charts
    assert male.panchang == female.panchang
    assert male.dasha == female.dasha
    assert male.birth_context == female.birth_context
    # Only this differs.
    assert male.gender_context != female.gender_context
