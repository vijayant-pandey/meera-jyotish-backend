"""Daily panchang for a place and moment.

Every value is computed from the ephemeris rather than stored. Verified against
drikpanchang.com for Jabalpur on 2026-09-20: sunrise, sunset and the nakshatra
end time match to the minute; tithi, yoga and karana end times agree within a
minute, the residue being a sub-arcsecond ayanamsha difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path

import swisseph as swe
from dateutil import tz

from app.config import get_settings

SETTINGS = get_settings()
DEFAULT_EPHE_PATH = Path(__file__).resolve().parents[2] / "ephe"

SIGN_NAMES = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]
TITHI_NAMES = [
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
    "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
    "Purnima",
]
NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra",
    "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
YOGA_NAMES = [
    "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma",
    "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
    "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha",
    "Shukla", "Brahma", "Indra", "Vaidhriti",
]
REPEATING_KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
FIXED_KARANAS = {0: "Kimstughna", 57: "Shakuni", 58: "Chatushpada", 59: "Naga"}
VARA_NAMES = [
    "Somawara", "Mangalawara", "Budhawara", "Guruwara", "Shukrawara", "Shaniwara", "Raviwara",
]
# The amanta month is named for the rashi the Sun occupies at the new moon that
# began it: Sun in Meena gives Chaitra, and so on round the zodiac.
LUNAR_MONTHS = [
    "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada", "Ashwina",
    "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna", "Chaitra",
]
SAMVATSARA_NAMES = [
    "Prabhava", "Vibhava", "Shukla", "Pramoduta", "Prajapati", "Angirasa", "Shrimukha",
    "Bhava", "Yuva", "Dhata", "Ishvara", "Bahudhanya", "Pramathi", "Vikrama", "Vrisha",
    "Chitrabhanu", "Svabhanu", "Tarana", "Parthiva", "Vyaya", "Sarvajit", "Sarvadhari",
    "Virodhi", "Vikriti", "Khara", "Nandana", "Vijaya", "Jaya", "Manmatha", "Durmukha",
    "Hevilambi", "Vilambi", "Vikari", "Sharvari", "Plava", "Shubhakrit", "Shobhakrit",
    "Krodhi", "Vishvavasu", "Parabhava", "Plavanga", "Kilaka", "Saumya", "Sadharana",
    "Virodhikrit", "Paridhavi", "Pramadi", "Ananda", "Rakshasa", "Nala", "Pingala",
    "Kalayukta", "Siddharthi", "Raudra", "Durmati", "Dundubhi", "Rudhirodgari", "Raktakshi",
    "Krodhana", "Akshaya",
]
GRAHAS = [
    ("Sun", "Surya", swe.SUN), ("Moon", "Chandra", swe.MOON), ("Mars", "Mangal", swe.MARS),
    ("Mercury", "Budha", swe.MERCURY), ("Jupiter", "Guru", swe.JUPITER),
    ("Venus", "Shukra", swe.VENUS), ("Saturn", "Shani", swe.SATURN),
    ("Rahu", "Rahu", swe.MEAN_NODE),
]
# Degrees from the Sun within which a graha is invisible (asta).
ASTA_ORBS = {"Moon": 12.0, "Mars": 17.0, "Mercury": 14.0, "Jupiter": 11.0,
             "Venus": 10.0, "Saturn": 15.0}

# Choghadiya divides the day and the night into eight parts each. A weekday's
# day sequence opens with that day's lord and steps forward through the hora
# order; its night sequence opens with the lord of the fifth weekday on and
# steps back two. Udvega, Kala and Roga are the inauspicious three.
CHOGHADIYA_ORDER = ["Udvega", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga"]
CHOGHADIYA_INAUSPICIOUS = {"Udvega", "Kala", "Roga"}

NAK_SPAN = 360 / 27


@dataclass
class Interval:
    name: str
    ends_at: datetime
    number: int = 0
    extra: str = ""


@dataclass
class Segment:
    """One division of a panchang band, clipped to the chart window."""

    name: str
    starts_at: datetime
    ends_at: datetime
    number: int = 0
    extra: str = ""


@dataclass
class Timeline:
    """The sunrise-to-sunrise bands behind the panchang chart."""

    sunrise: datetime
    sunset: datetime
    next_sunrise: datetime
    vara: str
    tithi: list[Segment]
    nakshatra: list[Segment]
    yoga: list[Segment]
    karana: list[Segment]
    choghadiya: list[Segment]


@dataclass
class GrahaPosition:
    name: str
    sanskrit: str
    sign: str
    longitude: float
    degree_in_sign: float
    motion: str          # Margi (direct) or Vakri (retrograde)
    visibility: str      # Udita (visible) or Asta (combust)


@dataclass
class PanchangResult:
    location: str
    latitude: float
    longitude: float
    timezone: str
    moment: datetime
    day: date_type
    sunrise: datetime
    sunset: datetime
    day_length: str
    vara: str
    tithi: Interval
    paksha: str
    nakshatra: Interval
    yoga: Interval
    karanas: list[Interval]
    moonsign: str
    sunsign: str
    amanta_month: str
    purnimanta_month: str
    shaka_samvat: str
    vikram_samvat: str
    gujarati_samvat: str
    pravishte: int
    ghati: int
    pal: int
    vipal: int
    timeline: Timeline
    grahas: list[GrahaPosition] = field(default_factory=list)


def _ephemeris_ready() -> None:
    swe.set_ephe_path(SETTINGS.swiss_ephe_path or str(DEFAULT_EPHE_PATH))
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def _julian(moment: datetime) -> float:
    utc = moment.astimezone(timezone.utc)
    hour = utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3_600_000_000
    return swe.julday(utc.year, utc.month, utc.day, hour, swe.GREG_CAL)


def _from_julian(jd: float, zone) -> datetime:
    year, month, day, hour = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=hour)
    # Panchang tables truncate to the minute rather than rounding.
    return base.astimezone(zone).replace(second=0, microsecond=0)


def _longitude(body: int, jd: float) -> float:
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    return swe.calc_ut(jd, body, flags)[0][0] % 360


def _speed(body: int, jd: float) -> float:
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL
    return swe.calc_ut(jd, body, flags)[0][3]


def _next_crossing(fn, jd_start: float, target: float, span: float = 3.0) -> float:
    """When the given angle next reaches the target, by bisection on the wrapped
    difference, which is monotone across a single span for these quantities."""
    low, high = jd_start, jd_start + span
    for _ in range(80):
        mid = (low + high) / 2
        if (fn(mid) - target) % 360 > 180:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _sun_event(jd_start: float, lat: float, lng: float, rising: bool) -> float:
    """Default flags mean upper limb with refraction, which is the definition
    published panchangs use; disc-centre would put sunrise a minute late."""
    flag = swe.CALC_RISE if rising else swe.CALC_SET
    result = swe.rise_trans(jd_start, swe.SUN, flag, (lng, lat, 0), 0, 0, swe.FLG_SWIEPH)
    return result[1][0]


def _tithi_name(index: int) -> str:
    """index is 0-29 across both pakshas."""
    if index == 29:
        return "Amavasya"
    if index == 14:
        return "Purnima"
    return TITHI_NAMES[index % 15]


def _karana_name(index: int) -> str:
    """index is 0-59 across the lunar month; four of the sixty are fixed."""
    return FIXED_KARANAS.get(index % 60, REPEATING_KARANAS[(index - 1) % 7])


def _band(fn, span: float, describe, jd_from: float, jd_to: float, zone) -> list[Segment]:
    """Consecutive divisions of `fn` - each `span` degrees wide - across a
    window, clipped at both ends. This is one row of the panchang chart."""
    divisions = int(round(360 / span))
    segments: list[Segment] = []
    jd = jd_from
    start = _from_julian(jd_from, zone)
    # A sunrise-to-sunrise window never holds more than a handful of divisions;
    # the cap is only a guard against a non-monotone angle.
    for _ in range(16):
        index = int(fn(jd) // span) % divisions
        crossing = _next_crossing(fn, jd, ((index + 1) * span) % 360)
        done = crossing >= jd_to
        name, extra = describe(index)
        segments.append(
            Segment(
                name=name,
                starts_at=start,
                ends_at=_from_julian(jd_to if done else crossing, zone),
                number=index + 1,
                extra=extra,
            )
        )
        if done:
            break
        start = _from_julian(crossing, zone)
        # Step past the boundary so the next search starts inside the new division.
        jd = crossing + 1e-6
    return segments


def _choghadiya(
    sunrise: datetime, sunset: datetime, next_sunrise: datetime, weekday: int
) -> list[Segment]:
    """Eight divisions of the day and eight of the night. `weekday` is 0 for
    Sunday, which is the ordering the classical rule is stated in."""
    segments: list[Segment] = []
    for start, end, first, step in (
        (sunrise, sunset, weekday * 3, 1),
        (sunset, next_sunrise, (weekday + 4) * 3, -2),
    ):
        width = (end - start) / 8
        for unit in range(8):
            name = CHOGHADIYA_ORDER[(first + step * unit) % 7]
            segments.append(
                Segment(
                    name=name,
                    starts_at=(start + width * unit).replace(second=0, microsecond=0),
                    ends_at=(start + width * (unit + 1)).replace(second=0, microsecond=0),
                    number=unit + 1,
                    extra="Inauspicious" if name in CHOGHADIYA_INAUSPICIOUS else "Auspicious",
                )
            )
    return segments


def compute_panchang(
    latitude: float,
    longitude: float,
    timezone_name: str,
    label: str = "",
    moment: datetime | None = None,
) -> PanchangResult:
    _ephemeris_ready()
    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")

    now = (moment or datetime.now(timezone.utc)).astimezone(zone)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    sunrise_jd = _sun_event(_julian(midnight), latitude, longitude, rising=True)
    sunset_jd = _sun_event(sunrise_jd, latitude, longitude, rising=False)
    # Half a day past sunrise is comfortably inside the day, so the next rise
    # found from there is tomorrow's. It closes the chart window.
    next_sunrise_jd = _sun_event(sunrise_jd + 0.5, latitude, longitude, rising=True)
    sunrise = _from_julian(sunrise_jd, zone)
    sunset = _from_julian(sunset_jd, zone)
    next_sunrise = _from_julian(next_sunrise_jd, zone)

    # The vara changes at sunrise, not at midnight. Before today's sunrise the
    # previous day's weekday still applies.
    vara_day = (midnight - timedelta(days=1)).date() if now < sunrise else midnight.date()
    vara = VARA_NAMES[vara_day.weekday()]

    jd_now = _julian(now)

    def elongation(jd: float) -> float:
        return (_longitude(swe.MOON, jd) - _longitude(swe.SUN, jd)) % 360

    def moon_lon(jd: float) -> float:
        return _longitude(swe.MOON, jd)

    def yoga_arc(jd: float) -> float:
        return (_longitude(swe.SUN, jd) + _longitude(swe.MOON, jd)) % 360

    # --- tithi -------------------------------------------------------------
    tithi_index = int(elongation(jd_now) // 12)
    tithi = Interval(
        name=_tithi_name(tithi_index),
        ends_at=_from_julian(_next_crossing(elongation, jd_now, (tithi_index + 1) * 12), zone),
        number=tithi_index + 1,
    )
    paksha = "Shukla Paksha" if tithi_index < 15 else "Krishna Paksha"

    # --- nakshatra ---------------------------------------------------------
    nak_index = int(moon_lon(jd_now) // NAK_SPAN)
    nak_position = moon_lon(jd_now) - nak_index * NAK_SPAN
    nakshatra = Interval(
        name=NAKSHATRA_NAMES[nak_index],
        ends_at=_from_julian(_next_crossing(moon_lon, jd_now, (nak_index + 1) * NAK_SPAN), zone),
        number=nak_index + 1,
        extra=f"Pada {int(nak_position // (NAK_SPAN / 4)) + 1}",
    )

    # --- yoga --------------------------------------------------------------
    yoga_index = int(yoga_arc(jd_now) // NAK_SPAN)
    yoga = Interval(
        name=YOGA_NAMES[yoga_index],
        ends_at=_from_julian(_next_crossing(yoga_arc, jd_now, (yoga_index + 1) * NAK_SPAN), zone),
        number=yoga_index + 1,
    )

    # --- karana: the current half-tithi and the one after it ---------------
    karanas: list[Interval] = []
    karana_index = int(elongation(jd_now) // 6)
    for step in range(2):
        index = karana_index + step
        name = _karana_name(index)
        karanas.append(
            Interval(
                name=name,
                ends_at=_from_julian(_next_crossing(elongation, jd_now, (index + 1) * 6), zone),
                number=index + 1,
            )
        )

    # --- lunar month -------------------------------------------------------
    # Walk back to the new moon that opened this lunar month, then name the
    # month from the rashi the Sun occupied at that moment.
    new_moon_jd = jd_now - (elongation(jd_now) / 360) * 29.53
    for _ in range(40):
        error = ((elongation(new_moon_jd) + 180) % 360) - 180
        new_moon_jd -= error / 12.19
    amanta_month = LUNAR_MONTHS[int(_longitude(swe.SUN, new_moon_jd) // 30)]
    # Purnimanta months run full-moon to full-moon, so a krishna paksha day
    # already belongs to the next month by that reckoning.
    purnimanta_month = (
        amanta_month if tithi_index < 15
        else LUNAR_MONTHS[(LUNAR_MONTHS.index(amanta_month) + 1) % 12]
    )

    # --- eras --------------------------------------------------------------
    sun_longitude = _longitude(swe.SUN, jd_now)
    shaka_year = now.year - 78 if now.month > 3 else now.year - 79
    vikram_year = shaka_year + 135
    gujarati_year = vikram_year - 1
    shaka_samvat = f"{shaka_year} {SAMVATSARA_NAMES[(shaka_year + 11) % 60]}"
    vikram_samvat = f"{vikram_year} {SAMVATSARA_NAMES[(vikram_year + 9) % 60]}"
    gujarati_samvat = f"{gujarati_year} {SAMVATSARA_NAMES[(gujarati_year + 8) % 60]}"

    # Pravishte (gate) is the solar day of the month: how many days since the Sun
    # entered the rashi it currently occupies, counting the ingress day as one.
    sign_start = int(sun_longitude // 30) * 30
    ingress_jd = jd_now
    for _ in range(60):
        error = ((_longitude(swe.SUN, ingress_jd) - sign_start + 180) % 360) - 180
        ingress_jd -= error / 0.9856
    pravishte = int(jd_now - ingress_jd) + 1

    # --- vedic clock: ghati/pal/vipal elapsed since sunrise ----------------
    since_sunrise = (now - sunrise).total_seconds()
    if since_sunrise < 0:
        since_sunrise += 86400
    ghati_units = since_sunrise / 24          # one ghati is 24 minutes
    ghati = int(ghati_units // 60)
    pal = int(ghati_units % 60)
    vipal = int((ghati_units * 60) % 60)

    # --- grahas ------------------------------------------------------------
    grahas: list[GrahaPosition] = []
    for name, sanskrit, body in GRAHAS:
        value = _longitude(body, jd_now)
        speed = _speed(body, jd_now)
        separation = abs((value - sun_longitude + 180) % 360 - 180)
        orb = ASTA_ORBS.get(name)
        grahas.append(
            GrahaPosition(
                name=name, sanskrit=sanskrit, sign=SIGN_NAMES[int(value // 30)],
                longitude=round(value, 2), degree_in_sign=round(value % 30, 2),
                motion="Vakri" if speed < 0 else "Margi",
                visibility="Asta" if orb is not None and separation <= orb else "Udita",
            )
        )
    ketu = (grahas[-1].longitude + 180) % 360
    grahas.append(
        GrahaPosition(
            name="Ketu", sanskrit="Ketu", sign=SIGN_NAMES[int(ketu // 30)],
            longitude=round(ketu, 2), degree_in_sign=round(ketu % 30, 2),
            motion="Vakri", visibility="Udita",
        )
    )

    # --- chart bands: sunrise to sunrise -----------------------------------
    timeline = Timeline(
        sunrise=sunrise,
        sunset=sunset,
        next_sunrise=next_sunrise,
        # The window opens at today's sunrise, so it carries today's vara even
        # when `now` is one of the small hours still belonging to yesterday.
        vara=VARA_NAMES[midnight.date().weekday()],
        tithi=_band(
            elongation, 12,
            lambda i: (_tithi_name(i), "Shukla" if i < 15 else "Krishna"),
            sunrise_jd, next_sunrise_jd, zone,
        ),
        nakshatra=_band(
            moon_lon, NAK_SPAN, lambda i: (NAKSHATRA_NAMES[i], ""),
            sunrise_jd, next_sunrise_jd, zone,
        ),
        yoga=_band(
            yoga_arc, NAK_SPAN, lambda i: (YOGA_NAMES[i], ""),
            sunrise_jd, next_sunrise_jd, zone,
        ),
        karana=_band(
            elongation, 6, lambda i: (_karana_name(i), ""),
            sunrise_jd, next_sunrise_jd, zone,
        ),
        choghadiya=_choghadiya(
            sunrise, sunset, next_sunrise, (midnight.date().weekday() + 1) % 7
        ),
    )

    total = int((sunset - sunrise).total_seconds())
    return PanchangResult(
        location=label or f"{latitude:.4f}, {longitude:.4f}",
        latitude=latitude, longitude=longitude, timezone=timezone_name,
        moment=now, day=now.date(), sunrise=sunrise, sunset=sunset,
        day_length=f"{total // 3600:02d}h {total % 3600 // 60:02d}m",
        vara=vara, tithi=tithi, paksha=paksha, nakshatra=nakshatra, yoga=yoga,
        karanas=karanas, moonsign=SIGN_NAMES[int(moon_lon(jd_now) // 30)],
        sunsign=SIGN_NAMES[int(sun_longitude // 30)],
        amanta_month=amanta_month, purnimanta_month=purnimanta_month,
        shaka_samvat=shaka_samvat, vikram_samvat=vikram_samvat,
        gujarati_samvat=gujarati_samvat, pravishte=pravishte,
        ghati=ghati, pal=pal, vipal=vipal, timeline=timeline, grahas=grahas,
    )
