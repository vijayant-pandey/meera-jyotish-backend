from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout

import swisseph as swe

from app.config import get_settings
from app.schemas import (
    ActiveDasha,
    AscendantPosition,
    Ayanamsha,
    BirthContext,
    Chart,
    ChartHouse,
    Dasha,
    DashaBalance,
    DivisionalChartEntry,
    DashaLevel,
    DashaPeriod,
    KundaliRequest,
    KundaliResponse,
    NakshatraInfo,
    Panchang,
    PlanetPosition,
)
from app.services.time_utils import resolve_birth_datetimes, utc_decimal_hour

with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    from jhora.horoscope.chart import charts as jhora_charts

SIGN_NAMES = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]

NAKSHATRA_NAMES = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
]

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

TITHI_BASE = [
    "Pratipada",
    "Dvitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Purnima",
]

YOGA_NAMES = [
    "Vishkumbha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarma",
    "Dhriti",
    "Shula",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyana",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Indra",
    "Vaidhriti",
]

REPEATING_KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]

DASHA_SEQUENCE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}

# Sign rulers, indexed by sign number - 1.
SIGN_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]
EXALTATION_SIGNS = {
    "Sun": 1, "Moon": 2, "Mars": 10, "Mercury": 6, "Jupiter": 4, "Venus": 12, "Saturn": 7,
}
OWN_SIGNS = {
    "Sun": {5}, "Moon": {4}, "Mars": {1, 8}, "Mercury": {3, 6},
    "Jupiter": {9, 12}, "Venus": {2, 7}, "Saturn": {10, 11},
}
# Natural (naisargika) friendships. Anything listed in neither set is neutral.
NATURAL_FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
NATURAL_ENEMIES = {
    "Sun": {"Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"},
    "Saturn": {"Sun", "Moon", "Mars"},
}
# Astadhyayi combustion orbs, in degrees of separation from the Sun.
COMBUSTION_ORBS = {
    "Moon": 12.0, "Mars": 17.0, "Mercury": 14.0,
    "Jupiter": 11.0, "Venus": 10.0, "Saturn": 15.0,
}
COMBUSTION_ORBS_RETROGRADE = {"Mercury": 12.0, "Venus": 8.0}

AYANAMSHA_MAP = {
    Ayanamsha.lahiri: swe.SIDM_LAHIRI,
    Ayanamsha.raman: swe.SIDM_RAMAN,
    Ayanamsha.kp: swe.SIDM_KRISHNAMURTI,
}

# AstroSage-compatible Vimshottari convention: one dasha year is 365.25 days.
# This must remain the single duration basis for Maha through Deha periods.
YEAR_DAYS = 365.25
NAKSHATRA_SPAN = 360 / 27
PADA_SPAN = NAKSHATRA_SPAN / 4

PLANET_DEFINITIONS = [
    ("Sun", "Su", swe.SUN),
    ("Moon", "Mo", swe.MOON),
    ("Mars", "Ma", swe.MARS),
    ("Mercury", "Me", swe.MERCURY),
    ("Jupiter", "Ju", swe.JUPITER),
    ("Venus", "Ve", swe.VENUS),
    ("Saturn", "Sa", swe.SATURN),
    ("Rahu", "Ra", swe.MEAN_NODE),
]

LOGGER = logging.getLogger(__name__)
SETTINGS = get_settings()
DEFAULT_EPHE_PATH = Path(__file__).resolve().parents[2] / "ephe"
_EPHEMERIS_FALLBACK_REPORTED = False
DASHA_LEVELS = [
    DashaLevel.mahadasha,
    DashaLevel.antardasha,
    DashaLevel.pratyantardasha,
    DashaLevel.sookshma,
    DashaLevel.prana,
    DashaLevel.deha,
]


def _report_ephemeris_fallback(return_flag: int, error_text: str) -> None:
    # swisseph answers a FLG_SWIEPH request with the Moshier ephemeris when the .se1
    # files are missing, and reports that only through the return flag and serr. Both
    # were being discarded, so a large accuracy loss was invisible. Warn once.
    global _EPHEMERIS_FALLBACK_REPORTED
    if _EPHEMERIS_FALLBACK_REPORTED or not return_flag & swe.FLG_MOSEPH:
        return
    _EPHEMERIS_FALLBACK_REPORTED = True
    LOGGER.warning(
        "Swiss Ephemeris files not found in %s, so positions fall back to the "
        "lower-accuracy Moshier ephemeris. Place .se1 files there or set "
        "SWISS_EPHE_PATH. swisseph reported: %s",
        SETTINGS.swiss_ephe_path or DEFAULT_EPHE_PATH,
        (error_text or "no detail").strip(),
    )


@dataclass
class ComputedPlanet:
    name: str
    abbreviation: str
    longitude: float
    speed: float


@dataclass(frozen=True)
class DivisionalChartSpec:
    key: str
    factor: int
    title: str
    focus: str
    chart_method: int = 1


CHART_PLANET_ORDER = [abbreviation for _, abbreviation, _ in PLANET_DEFINITIONS] + ["Ke"]
DIVISIONAL_CHART_SPECS = [
    DivisionalChartSpec("D1", 1, "D-1 (Rashi)", "Physical body and overall life"),
    DivisionalChartSpec("D2", 2, "D-2 (Hora)", "Wealth and financial prosperity", chart_method=2),
    DivisionalChartSpec("D3", 3, "D-3 (Drekkana)", "Siblings, courage, and short journeys"),
    DivisionalChartSpec("D4", 4, "D-4 (Chaturthamsa)", "Luck, assets, property, and home"),
    DivisionalChartSpec("D5", 5, "D-5 (Panchamsha)", "Fame, power, authority, and children"),
    DivisionalChartSpec("D6", 6, "D-6 (Shashthamsa)", "Health, disease, enemies, and obstacles"),
    DivisionalChartSpec("D7", 7, "D-7 (Saptamsa)", "Children, grandchildren, and creative projects"),
    DivisionalChartSpec("D8", 8, "D-8 (Ashtamsa)", "Longevity, sudden events, and the occult"),
    DivisionalChartSpec("D9", 9, "D-9 (Navamsa)", "Marriage, partnerships, and inner strength"),
    DivisionalChartSpec("D10", 10, "D-10 (Dashamsa)", "Career, profession, and status"),
    DivisionalChartSpec("D11", 11, "D-11 (Ekadashamsa)", "Gains and income", chart_method=1),
    DivisionalChartSpec("D12", 12, "D-12 (Dwadashamsa)", "Parents, ancestors, and lineage"),
    DivisionalChartSpec("D16", 16, "D-16 (Shodashamsa)", "Vehicles, comforts, and luxuries"),
    DivisionalChartSpec("D20", 20, "D-20 (Vimsamsa)", "Spiritual and religious practice"),
    DivisionalChartSpec("D24", 24, "D-24 (Chaturvimsamsa)", "Education, learning, and knowledge", chart_method=3),
    DivisionalChartSpec("D27", 27, "D-27 (Bhamsha / Nakshatramsa)", "Strengths, weaknesses, and vitality"),
    DivisionalChartSpec("D30", 30, "D-30 (Trimshamsa)", "Misfortune, debts, hidden flaws, and suffering"),
    DivisionalChartSpec("D40", 40, "D-40 (Khavedamsa)", "Auspicious effects, karma, and maternal lineage"),
    DivisionalChartSpec("D45", 45, "D-45 (Akshavedamsa)", "Character, overall life, and paternal lineage"),
    DivisionalChartSpec("D60", 60, "D-60 (Shashtyamsa)", "Past-life karma and deepest destiny"),
]


def normalize_degrees(value: float) -> float:
    return value % 360


def sign_number_from_longitude(longitude: float) -> int:
    return int(normalize_degrees(longitude) // 30) + 1


def degree_in_sign(longitude: float) -> float:
    # 6 decimals is ~0.004 arcsec, so the UI can render exact degree-minute-second
    # values. At 4 decimals the rounding was ~0.36 arcsec and could shift a
    # displayed second, and it also fed the divisional-chart input.
    return round(normalize_degrees(longitude) % 30, 6)


def house_number_for_sign(sign_number: int, asc_sign_number: int) -> int:
    return ((sign_number - asc_sign_number) % 12) + 1


def planet_relation(name: str, sign_number: int) -> str | None:
    exaltation_sign = EXALTATION_SIGNS.get(name)
    if exaltation_sign is None:
        return None
    if sign_number == exaltation_sign:
        return "Exalted"
    if sign_number == ((exaltation_sign - 1 + 6) % 12) + 1:
        return "Debilitated"
    if sign_number in OWN_SIGNS[name]:
        return "Own"
    lord = SIGN_LORDS[sign_number - 1]
    if lord in NATURAL_FRIENDS[name]:
        return "Friendly"
    if lord in NATURAL_ENEMIES[name]:
        return "Enemy"
    return "Neutral"


def is_combust(name: str, longitude: float, sun_longitude: float, retrograde: bool) -> bool:
    orb = COMBUSTION_ORBS.get(name)
    if orb is None:
        return False
    if retrograde:
        orb = COMBUSTION_ORBS_RETROGRADE.get(name, orb)
    separation = normalize_degrees(longitude - sun_longitude)
    if separation > 180:
        separation = 360 - separation
    return separation <= orb


def nakshatra_index_and_fraction(longitude: float) -> tuple[int, float]:
    # Scale into nakshatra units before splitting. 360/27 has no exact float
    # representation and lands slightly high, so dividing by it pushes the exact
    # boundary degrees (40, 80, 120 ...) into the previous nakshatra. Multiplying
    # first keeps those boundaries exact.
    position = normalize_degrees(longitude) * 27 / 360
    index = min(int(position), 26)
    return index, position - index


def nakshatra_info(longitude: float) -> NakshatraInfo:
    index, fraction = nakshatra_index_and_fraction(longitude)
    pada = min(int(fraction * 4), 3) + 1
    lord = DASHA_SEQUENCE[index % len(DASHA_SEQUENCE)]
    return NakshatraInfo(
        number=index + 1,
        name=NAKSHATRA_NAMES[index],
        pada=pada,
        lord=lord,
    )


def panchang_from_longitudes(sun_longitude: float, moon_longitude: float, local_dt: datetime) -> Panchang:
    lunar_phase = normalize_degrees(moon_longitude - sun_longitude)
    tithi_index = int(lunar_phase // 12)
    paksha = "Shukla" if tithi_index < 15 else "Krishna"
    tithi_name = TITHI_BASE[tithi_index % 15]

    if tithi_index == 29:
        tithi = "Amavasya"
    elif tithi_index == 14:
        tithi = "Purnima"
    else:
        tithi = f"{paksha} {tithi_name}"

    yoga_index = min(int(normalize_degrees(sun_longitude + moon_longitude) * 27 / 360), 26)
    karana_index = int(lunar_phase // 6)
    if karana_index == 0:
        karana = "Kimstughna"
    elif 1 <= karana_index <= 56:
        karana = REPEATING_KARANAS[(karana_index - 1) % len(REPEATING_KARANAS)]
    elif karana_index == 57:
        karana = "Shakuni"
    elif karana_index == 58:
        karana = "Chatushpada"
    else:
        karana = "Naga"

    moon_nakshatra = nakshatra_info(moon_longitude)
    return Panchang(
        tithi=tithi,
        vara=WEEKDAY_NAMES[local_dt.weekday()],
        nakshatra=f"{moon_nakshatra.name} Pada {moon_nakshatra.pada}",
        yoga=YOGA_NAMES[yoga_index],
        karana=karana,
    )


def _rotated_dasha_sequence(start_lord: str) -> list[str]:
    start_index = DASHA_SEQUENCE.index(start_lord)
    return DASHA_SEQUENCE[start_index:] + DASHA_SEQUENCE[:start_index]


def _dasha_label(path: list[str]) -> str:
    return " / ".join(path)


def _build_dasha_period(
    lord: str,
    start: datetime,
    end: datetime,
    level: DashaLevel,
    path: list[str],
) -> DashaPeriod:
    return DashaPeriod(
        level=level,
        lord=lord,
        label=_dasha_label(path),
        path=path,
        start=start,
        end=end,
    )


def _subdivide_period(parent: DashaPeriod, level: DashaLevel) -> list[DashaPeriod]:
    sequence = _rotated_dasha_sequence(parent.lord)
    parent_duration_seconds = (parent.end - parent.start).total_seconds()
    cursor = parent.start
    periods: list[DashaPeriod] = []

    for index, lord in enumerate(sequence):
        if index == len(sequence) - 1:
            child_end = parent.end
        else:
            child_duration_seconds = parent_duration_seconds * DASHA_YEARS[lord] / 120
            child_end = cursor + timedelta(seconds=child_duration_seconds)
        child_path = [*parent.path, lord]
        periods.append(_build_dasha_period(lord, cursor, child_end, level, child_path))
        cursor = child_end

    return periods


def _find_active_period(periods: list[DashaPeriod], moment: datetime) -> DashaPeriod:
    for period in periods:
        if period.start <= moment < period.end:
            return period
    # Clamp to the correct end. A moment before the timeline begins belongs to the
    # first period; only a moment past the end belongs to the last one.
    return periods[0] if moment < periods[0].start else periods[-1]


def _active_dasha_path(root_periods: list[DashaPeriod], moment: datetime) -> list[DashaPeriod]:
    active_periods: list[DashaPeriod] = []
    current_periods = root_periods

    for level in DASHA_LEVELS:
        active = _find_active_period(current_periods, moment)
        active_periods.append(active)
        if level == DashaLevel.deha:
            break
        next_level = DASHA_LEVELS[DASHA_LEVELS.index(level) + 1]
        current_periods = _subdivide_period(active, next_level)

    return active_periods


def vimshottari_dasha(moon_longitude: float, local_dt: datetime) -> Dasha:
    moon_nakshatra = nakshatra_info(moon_longitude)
    lord = moon_nakshatra.lord
    _, fraction_elapsed = nakshatra_index_and_fraction(moon_longitude)
    remaining_fraction = 1 - fraction_elapsed
    mahadasha_years = DASHA_YEARS[lord]
    mahadasha_elapsed_days = mahadasha_years * fraction_elapsed * YEAR_DAYS
    mahadasha_start = local_dt - timedelta(days=mahadasha_elapsed_days)
    mahadasha_end = mahadasha_start + timedelta(days=mahadasha_years * YEAR_DAYS)

    periods: list[DashaPeriod] = []
    total_cycle_end = mahadasha_start + timedelta(days=120 * YEAR_DAYS)
    cursor = mahadasha_start
    rotated_sequence = _rotated_dasha_sequence(lord)
    for index, period_lord in enumerate(rotated_sequence):
        if index == len(rotated_sequence) - 1:
            end = total_cycle_end
        else:
            end = cursor + timedelta(days=DASHA_YEARS[period_lord] * YEAR_DAYS)
        periods.append(
            _build_dasha_period(
                period_lord,
                cursor,
                end,
                DashaLevel.mahadasha,
                [period_lord],
            )
        )
        cursor = end

    active_periods = _active_dasha_path(periods, local_dt)
    return Dasha(
        system="Vimshottari",
        year_days=YEAR_DAYS,
        sequence=DASHA_SEQUENCE,
        years_by_lord=DASHA_YEARS,
        balance_at_birth=DashaBalance(
            lord=lord,
            start=mahadasha_start,
            end=mahadasha_end,
            elapsed_days=round(mahadasha_elapsed_days, 6),
            remaining_days=round(mahadasha_years * remaining_fraction * YEAR_DAYS, 6),
            remaining_years=round(mahadasha_years * remaining_fraction, 6),
            remaining_nakshatra_fraction=round(remaining_fraction, 9),
        ),
        active_at_birth=ActiveDasha(
            mahadasha=active_periods[0].lord,
            antardasha=active_periods[1].lord,
            pratyantardasha=active_periods[2].lord,
            sookshma=active_periods[3].lord,
            prana=active_periods[4].lord,
            deha=active_periods[5].lord,
            mahadasha_period=active_periods[0],
            antardasha_period=active_periods[1],
            pratyantardasha_period=active_periods[2],
            sookshma_period=active_periods[3],
            prana_period=active_periods[4],
            deha_period=active_periods[5],
        ),
        periods=periods,
    )


def build_chart(asc_sign_number: int, planets: list[PlanetPosition]) -> Chart:
    houses: list[ChartHouse] = []
    for house_number in range(1, 13):
        sign_number = ((asc_sign_number + house_number - 2) % 12) + 1
        house_planets = [
            planet.abbreviation
            for planet in planets
            if planet.house_number == house_number
        ]
        houses.append(
            ChartHouse(
                house_number=house_number,
                sign_number=sign_number,
                sign_name=SIGN_NAMES[sign_number - 1],
                planets=house_planets,
            )
        )
    return Chart(
        style="north-india",
        ascendant_sign_number=asc_sign_number,
        ascendant_sign_name=SIGN_NAMES[asc_sign_number - 1],
        houses=houses,
    )


def build_chart_from_sign_map(asc_sign_number: int, sign_by_planet: dict[str, int]) -> Chart:
    houses: list[ChartHouse] = []
    for house_number in range(1, 13):
        sign_number = ((asc_sign_number + house_number - 2) % 12) + 1
        house_planets = [
            abbreviation
            for abbreviation in CHART_PLANET_ORDER
            if sign_by_planet.get(abbreviation) is not None
            and house_number_for_sign(sign_by_planet[abbreviation], asc_sign_number) == house_number
        ]
        houses.append(
            ChartHouse(
                house_number=house_number,
                sign_number=sign_number,
                sign_name=SIGN_NAMES[sign_number - 1],
                planets=house_planets,
            )
        )
    return Chart(
        style="north-india",
        ascendant_sign_number=asc_sign_number,
        ascendant_sign_name=SIGN_NAMES[asc_sign_number - 1],
        houses=houses,
    )


def bhava_madhya_longitudes(asc_longitude: float, mc_longitude: float) -> list[float]:
    # Sripati paddhati: the Lagna and the MC are bhava madhyas, and each quadrant
    # between them is trisected to give the remaining madhyas. That trisection is the
    # Porphyry construction, computed here as plain longitude arithmetic so it stays
    # defined at every latitude instead of degenerating near the poles like Placidus.
    asc = normalize_degrees(asc_longitude)
    mc = normalize_degrees(mc_longitude)
    ic = normalize_degrees(mc + 180)
    desc = normalize_degrees(asc + 180)
    asc_to_ic_third = normalize_degrees(ic - asc) / 3
    ic_to_desc_third = normalize_degrees(desc - ic) / 3
    return [
        asc,
        normalize_degrees(asc + asc_to_ic_third),
        normalize_degrees(asc + 2 * asc_to_ic_third),
        ic,
        normalize_degrees(ic + ic_to_desc_third),
        normalize_degrees(ic + 2 * ic_to_desc_third),
        desc,
        normalize_degrees(desc + asc_to_ic_third),
        normalize_degrees(desc + 2 * asc_to_ic_third),
        mc,
        normalize_degrees(mc + ic_to_desc_third),
        normalize_degrees(mc + 2 * ic_to_desc_third),
    ]


def bhava_sandhi_longitudes(madhyas: list[float]) -> list[float]:
    # A bhava boundary sits halfway between two consecutive madhyas. Bhavas are
    # therefore unequal, and the Lagna degree is the midpoint of the first bhava
    # rather than a fixed 15 degrees from its edges.
    return [
        normalize_degrees(
            madhyas[index - 1] + normalize_degrees(madhyas[index] - madhyas[index - 1]) / 2
        )
        for index in range(12)
    ]


def bhava_house_number(longitude: float, sandhis: list[float]) -> int:
    for index in range(12):
        start = sandhis[index]
        span = normalize_degrees(sandhis[(index + 1) % 12] - start)
        if normalize_degrees(longitude - start) < span:
            return index + 1
    return 12


def build_bhava_chalit_chart(
    asc_longitude: float,
    mc_longitude: float,
    planets: list[PlanetPosition],
) -> Chart:
    asc_sign_number = sign_number_from_longitude(asc_longitude)
    sandhis = bhava_sandhi_longitudes(bhava_madhya_longitudes(asc_longitude, mc_longitude))
    houses: list[ChartHouse] = []
    for house_number in range(1, 13):
        sign_number = ((asc_sign_number + house_number - 2) % 12) + 1
        houses.append(
            ChartHouse(
                house_number=house_number,
                sign_number=sign_number,
                sign_name=SIGN_NAMES[sign_number - 1],
                planets=[
                    planet.abbreviation
                    for planet in planets
                    if bhava_house_number(planet.longitude, sandhis) == house_number
                ],
            )
        )
    return Chart(
        style="north-india",
        ascendant_sign_number=asc_sign_number,
        ascendant_sign_name=SIGN_NAMES[asc_sign_number - 1],
        houses=houses,
    )


def build_divisional_input(asc_longitude: float, planets: list[PlanetPosition]) -> list[list[object]]:
    positions: list[list[object]] = [
        ["L", [sign_number_from_longitude(asc_longitude) - 1, degree_in_sign(asc_longitude)]]
    ]
    for abbreviation in CHART_PLANET_ORDER:
        planet = next(item for item in planets if item.abbreviation == abbreviation)
        positions.append([planet.abbreviation, [planet.sign_number - 1, planet.degree_in_sign]])
    return positions


def build_divisional_charts(
    asc_longitude: float,
    mc_longitude: float,
    base_chart: Chart,
    planets: list[PlanetPosition],
) -> list[DivisionalChartEntry]:
    rasi_positions = build_divisional_input(asc_longitude, planets)
    entries: list[DivisionalChartEntry] = []

    for spec in DIVISIONAL_CHART_SPECS:
        if spec.factor == 1:
            chart = base_chart
        else:
            varga_positions = jhora_charts.divisional_positions_from_rasi_positions(
                rasi_positions,
                divisional_chart_factor=spec.factor,
                chart_method=spec.chart_method,
            )
            asc_entry = next(item for item in varga_positions if item[0] == "L")
            asc_sign_number = int(asc_entry[1][0]) + 1
            sign_by_planet = {
                str(planet): int(data[0]) + 1
                for planet, data in varga_positions
                if planet != "L"
            }
            chart = build_chart_from_sign_map(asc_sign_number, sign_by_planet)

        entries.append(
            DivisionalChartEntry(
                key=spec.key,
                factor=spec.factor,
                title=spec.title,
                focus=spec.focus,
                chart=chart,
            )
        )

    entries.insert(
        1,
        DivisionalChartEntry(
            key="CHALIT",
            factor=0,
            title="Bhava Chalit",
            focus="Planets placed by Sripati bhava boundaries",
            chart=build_bhava_chalit_chart(asc_longitude, mc_longitude, planets),
        ),
    )
    return entries


def calculate_kundali(payload: KundaliRequest) -> KundaliResponse:
    swe.set_ephe_path(SETTINGS.swiss_ephe_path or str(DEFAULT_EPHE_PATH))
    local_dt, utc_dt = resolve_birth_datetimes(
        payload.birth_date,
        payload.birth_time12h,
        payload.meridiem,
        payload.place.timezone,
    )
    julian_day_ut = swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_decimal_hour(utc_dt),
        swe.GREG_CAL,
    )

    swe.set_sid_mode(AYANAMSHA_MAP[payload.ayanamsha], 0, 0)
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL
    _, ascmc = swe.houses_ex(julian_day_ut, payload.place.lat, payload.place.lng, b"P", flags)
    asc_longitude = normalize_degrees(ascmc[0])
    mc_longitude = normalize_degrees(ascmc[1])
    asc_sign_number = sign_number_from_longitude(asc_longitude)

    computed_planets: list[ComputedPlanet] = []
    for name, abbreviation, planet_id in PLANET_DEFINITIONS:
        values, return_flag, error_text = swe.calc_ut(julian_day_ut, planet_id, flags)
        _report_ephemeris_fallback(return_flag, error_text)
        computed_planets.append(
            ComputedPlanet(
                name=name,
                abbreviation=abbreviation,
                longitude=normalize_degrees(values[0]),
                speed=values[3],
            )
        )

    rahu = next(planet for planet in computed_planets if planet.name == "Rahu")
    ketu_longitude = normalize_degrees(rahu.longitude + 180)
    computed_planets.append(
        ComputedPlanet(name="Ketu", abbreviation="Ke", longitude=ketu_longitude, speed=rahu.speed)
    )

    sun_longitude = next(
        planet.longitude for planet in computed_planets if planet.name == "Sun"
    )
    planet_models: list[PlanetPosition] = []
    for planet in computed_planets:
        sign_number = sign_number_from_longitude(planet.longitude)
        house_number = house_number_for_sign(sign_number, asc_sign_number)
        retrograde = planet.speed < 0
        planet_models.append(
            PlanetPosition(
                name=planet.name,
                abbreviation=planet.abbreviation,
                longitude=round(planet.longitude, 4),
                sign_number=sign_number,
                sign_name=SIGN_NAMES[sign_number - 1],
                degree_in_sign=degree_in_sign(planet.longitude),
                house_number=house_number,
                retrograde=retrograde,
                nakshatra=nakshatra_info(planet.longitude),
                combust=is_combust(planet.name, planet.longitude, sun_longitude, retrograde),
                relation=planet_relation(planet.name, sign_number),
            )
        )

    # Use the unrounded longitudes here. PlanetPosition rounds to 4 decimals for
    # display, and the dasha timeline magnifies Moon error by roughly 274 days per
    # degree, so that rounding alone moves every period boundary by minutes.
    sun = next(planet for planet in computed_planets if planet.name == "Sun")
    moon = next(planet for planet in computed_planets if planet.name == "Moon")

    base_chart = build_chart(asc_sign_number, planet_models)

    return KundaliResponse(
        birth_context=BirthContext(
            local_datetime=local_dt,
            utc_datetime=utc_dt,
            timezone=payload.place.timezone,
            latitude=payload.place.lat,
            longitude=payload.place.lng,
            ayanamsha=payload.ayanamsha,
            julian_day_ut=round(julian_day_ut, 6),
        ),
        ascendant=AscendantPosition(
            longitude=round(asc_longitude, 4),
            sign_number=asc_sign_number,
            sign_name=SIGN_NAMES[asc_sign_number - 1],
            degree_in_sign=degree_in_sign(asc_longitude),
            nakshatra=nakshatra_info(asc_longitude),
        ),
        chart=base_chart,
        divisional_charts=build_divisional_charts(
            asc_longitude,
            mc_longitude,
            base_chart,
            planet_models,
        ),
        planets=planet_models,
        panchang=panchang_from_longitudes(sun.longitude, moon.longitude, local_dt),
        # Dasha durations are astronomical intervals. Calculate them in UTC so
        # daylight-saving transitions cannot alter a period boundary.
        dasha=vimshottari_dasha(moon.longitude, utc_dt),
    )
