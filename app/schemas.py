from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class Precision(str, Enum):
    city = "city"
    admin = "admin"
    country = "country"
    manual = "manual"


class Source(str, Enum):
    google = "google"
    osm = "osm"
    manual = "manual"


class Meridiem(str, Enum):
    am = "AM"
    pm = "PM"


class Ayanamsha(str, Enum):
    lahiri = "LAHIRI"
    raman = "RAMAN"
    kp = "KP"


class PlaceSuggestion(CamelModel):
    provider: Source
    provider_id: str
    label: str
    secondary_label: str | None = None
    precision: Precision
    country_code: str | None = None
    country: str | None = None


class ResolvePlaceRequest(CamelModel):
    provider: Source
    provider_id: str


class ResolvedPlace(CamelModel):
    label: str
    lat: float
    lng: float
    timezone: str
    country_code: str | None = None
    country: str | None = None
    admin: str | None = None
    precision: Precision
    source: Source

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        if not -90 <= value <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        return round(value, 6)

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, value: float) -> float:
        if not -180 <= value <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        return round(value, 6)


class KundaliRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    birth_date: date
    birth_time12h: str
    meridiem: Meridiem
    place: ResolvedPlace
    ayanamsha: Ayanamsha = Ayanamsha.lahiri


class NakshatraInfo(CamelModel):
    number: int
    name: str
    pada: int
    lord: str


class PlanetPosition(CamelModel):
    name: str
    abbreviation: str
    longitude: float
    sign_number: int
    sign_name: str
    degree_in_sign: float
    house_number: int
    retrograde: bool
    nakshatra: NakshatraInfo


class Panchang(CamelModel):
    tithi: str
    vara: str
    nakshatra: str
    yoga: str
    karana: str


class DashaLevel(str, Enum):
    mahadasha = "mahadasha"
    antardasha = "antardasha"
    pratyantardasha = "pratyantardasha"
    sookshma = "sookshma"
    prana = "prana"
    deha = "deha"


class DashaPeriod(CamelModel):
    level: DashaLevel
    lord: str
    label: str
    path: list[str]
    start: datetime
    end: datetime


class DashaBalance(CamelModel):
    lord: str
    start: datetime
    end: datetime
    elapsed_days: float
    remaining_days: float
    remaining_years: float
    remaining_nakshatra_fraction: float


class ActiveDasha(CamelModel):
    mahadasha: str
    antardasha: str
    pratyantardasha: str
    sookshma: str
    prana: str
    deha: str | None = None
    mahadasha_period: DashaPeriod
    antardasha_period: DashaPeriod
    pratyantardasha_period: DashaPeriod
    sookshma_period: DashaPeriod
    prana_period: DashaPeriod
    deha_period: DashaPeriod | None = None


class Dasha(CamelModel):
    system: str
    year_days: float = 365.25
    sequence: list[str]
    years_by_lord: dict[str, int]
    balance_at_birth: DashaBalance
    active_at_birth: ActiveDasha
    periods: list[DashaPeriod]


class ChartHouse(CamelModel):
    house_number: int
    sign_number: int
    sign_name: str
    planets: list[str]


class Chart(CamelModel):
    style: str
    ascendant_sign_number: int
    ascendant_sign_name: str
    houses: list[ChartHouse]


class DivisionalChartEntry(CamelModel):
    key: str
    factor: int
    title: str
    focus: str
    chart: Chart


class BirthContext(CamelModel):
    local_datetime: datetime
    utc_datetime: datetime
    timezone: str
    latitude: float
    longitude: float
    ayanamsha: Ayanamsha
    julian_day_ut: float


class KundaliResponse(CamelModel):
    birth_context: BirthContext
    chart: Chart
    divisional_charts: list[DivisionalChartEntry]
    planets: list[PlanetPosition]
    panchang: Panchang
    dasha: Dasha


class KundaliReport(CamelModel):
    id: str
    created_at: datetime
    user_id: str
    request: KundaliRequest
    result: KundaliResponse


class KundaliChartRouteResponse(CamelModel):
    report_id: str
    created_at: datetime
    name: str
    birth_context: BirthContext
    selected_chart: DivisionalChartEntry
    available_charts: list[DivisionalChartEntry]


class DashaRouteResponse(CamelModel):
    report_id: str
    created_at: datetime
    name: str
    birth_context: BirthContext
    dasha: Dasha


class AuthUser(CamelModel):
    id: str
    name: str
    email: str
    phone: str
    created_at: datetime


class SignupRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(CamelModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=256)
