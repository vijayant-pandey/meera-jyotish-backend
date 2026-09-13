from datetime import date

from app.schemas import Ayanamsha, KundaliRequest, Meridiem, Precision, ResolvedPlace, Source
from app.services.astrology import calculate_kundali


def build_payload() -> KundaliRequest:
    return KundaliRequest(
        name="Ada Lovelace",
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
