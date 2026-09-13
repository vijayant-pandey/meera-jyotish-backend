from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from timezonefinder import TimezoneFinder

from app.config import Settings
from app.schemas import PlaceSuggestion, Precision, ResolvedPlace, Source

LOCALITY_KEYS = ("city", "town", "village", "municipality", "hamlet", "locality", "suburb")
ADMIN_KEYS = ("state", "region", "state_district", "county")


def _classify_google_precision(types: list[str]) -> Precision:
    type_set = set(types)
    if "country" in type_set:
        return Precision.country
    if {"locality", "postal_town", "sublocality", "neighborhood"} & type_set:
        return Precision.city
    return Precision.admin


def _classify_osm_precision(item: dict[str, Any]) -> Precision:
    raw_type = item.get("addresstype") or item.get("type") or ""
    if raw_type == "country":
        return Precision.country
    if raw_type in {"city", "town", "village", "municipality", "hamlet"}:
        return Precision.city
    return Precision.admin


def _first_address_value(address: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _osm_display_parts(item: dict[str, Any]) -> tuple[str, str | None, str | None]:
    address = item.get("address") or {}
    display_name = str(item.get("display_name") or "")
    primary = _first_address_value(address, LOCALITY_KEYS) or str(item.get("name") or "").strip()
    if not primary:
        primary = display_name.split(",", maxsplit=1)[0].strip() or "Selected place"

    admin = _first_address_value(address, ADMIN_KEYS)
    country = address.get("country") if isinstance(address.get("country"), str) else None
    return primary, admin, country


def _osm_label(item: dict[str, Any]) -> str:
    primary, admin, country = _osm_display_parts(item)
    parts = [primary]
    for value in (admin, country):
        if value and value.casefold() not in {part.casefold() for part in parts}:
            parts.append(value)
    return ", ".join(parts)


def _osm_secondary_label(item: dict[str, Any], precision: Precision) -> str:
    _, admin, country = _osm_display_parts(item)
    match_type = "City match" if precision is Precision.city else "Area match"
    context = ", ".join(value for value in (admin, country) if value)
    return f"{match_type} - {context}" if context else match_type


def _osm_suggestions(query: str, payload: list[dict[str, Any]]) -> list[PlaceSuggestion]:
    normalized_query = " ".join(query.casefold().split())
    ranked: list[tuple[tuple[int, int, float], str, PlaceSuggestion]] = []

    for item in payload:
        address = item.get("address") or {}
        precision = _classify_osm_precision(item)
        primary, _, _ = _osm_display_parts(item)
        primary_key = " ".join(primary.casefold().split())
        exact_match = primary_key == normalized_query
        precision_rank = {Precision.city: 0, Precision.admin: 1, Precision.country: 2}[precision]
        importance = float(item.get("importance") or 0)
        suggestion = PlaceSuggestion(
            provider=Source.osm,
            provider_id=f"{item['osm_type']}:{item['osm_id']}",
            label=_osm_label(item),
            secondary_label=_osm_secondary_label(item, precision),
            precision=precision,
            country_code=(address.get("country_code") or "").upper() or None,
            country=address.get("country"),
        )
        # A city record is more appropriate for a birth place than its overlapping boundary record.
        rank = (0 if exact_match else 1, precision_rank, -importance)
        dedupe_key = f"{primary_key}|{suggestion.country_code or ''}"
        ranked.append((rank, dedupe_key, suggestion))

    ranked.sort(key=lambda entry: entry[0])
    unique: list[PlaceSuggestion] = []
    seen: set[str] = set()
    for _, dedupe_key, suggestion in ranked:
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(suggestion)
    return unique


class GeolocationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timezone_finder = TimezoneFinder()

    async def autocomplete(self, query: str) -> list[PlaceSuggestion]:
        query = query.strip()
        if len(query) < 2:
            return []

        suggestions: list[PlaceSuggestion] = []

        if self.settings.google_enabled:
            google_suggestions = await self._google_autocomplete(query)
            if google_suggestions:
                suggestions.extend(google_suggestions)

        if not suggestions:
            suggestions.extend(await self._osm_autocomplete(query))

        return suggestions[:6]

    async def resolve(self, provider: Source, provider_id: str) -> ResolvedPlace:
        if provider is Source.google and self.settings.google_enabled:
            return await self._google_resolve(provider_id)
        if provider is Source.osm:
            return await self._osm_resolve(provider_id)
        raise ValueError("Unsupported place provider.")

    async def _google_autocomplete(self, query: str) -> list[PlaceSuggestion]:
        params = {
            "input": query,
            "key": self.settings.google_places_api_key,
            "language": "en",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        predictions = payload.get("predictions", [])
        suggestions: list[PlaceSuggestion] = []
        for item in predictions:
            precision = _classify_google_precision(item.get("types", []))
            secondary = None
            terms = item.get("terms") or []
            if len(terms) > 1:
                secondary = ", ".join(part["value"] for part in terms[1:])
            suggestions.append(
                PlaceSuggestion(
                    provider=Source.google,
                    provider_id=item["place_id"],
                    label=item["description"],
                    secondary_label=secondary,
                    precision=precision,
                )
            )
        return suggestions

    async def _google_resolve(self, place_id: str) -> ResolvedPlace:
        params = {
            "place_id": place_id,
            "fields": "address_component,formatted_address,geometry,type",
            "key": self.settings.google_places_api_key,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

            result = payload.get("result") or {}
            location = ((result.get("geometry") or {}).get("location") or {})
            lat = float(location["lat"])
            lng = float(location["lng"])
            timezone_response = await client.get(
                "https://maps.googleapis.com/maps/api/timezone/json",
                params={
                    "location": f"{lat},{lng}",
                    "timestamp": int(datetime.now(UTC).timestamp()),
                    "key": self.settings.google_timezone_api_key,
                },
            )
            timezone_response.raise_for_status()
            timezone_payload = timezone_response.json()

        timezone_name = timezone_payload.get("timeZoneId") or self._fallback_timezone(lat, lng)
        components = result.get("address_components") or []
        country_code = None
        country = None
        admin = None
        for component in components:
            types = component.get("types", [])
            if "country" in types:
                country_code = component.get("short_name")
                country = component.get("long_name")
            if "administrative_area_level_1" in types and admin is None:
                admin = component.get("long_name")
        precision = _classify_google_precision(result.get("types", []))
        return ResolvedPlace(
            label=result.get("formatted_address", place_id),
            lat=lat,
            lng=lng,
            timezone=timezone_name,
            country_code=country_code,
            country=country,
            admin=admin,
            precision=precision,
            source=Source.google,
        )

    async def _osm_autocomplete(self, query: str) -> list[PlaceSuggestion]:
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 6,
        }
        headers = {"User-Agent": self.settings.nominatim_user_agent}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        return _osm_suggestions(query, payload)

    async def _osm_resolve(self, provider_id: str) -> ResolvedPlace:
        osm_type, osm_id = provider_id.split(":", maxsplit=1)
        prefix = {"relation": "R", "way": "W", "node": "N"}.get(osm_type)
        if prefix is None:
            raise ValueError("Unsupported OpenStreetMap identifier.")

        params = {
            "osm_ids": f"{prefix}{osm_id}",
            "format": "json",
            "addressdetails": 1,
        }
        headers = {"User-Agent": self.settings.nominatim_user_agent}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/lookup",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        if not payload:
            raise ValueError("Place could not be resolved.")

        item = payload[0]
        address = item.get("address") or {}
        lat = float(item["lat"])
        lng = float(item["lon"])
        return ResolvedPlace(
            label=_osm_label(item),
            lat=lat,
            lng=lng,
            timezone=self._fallback_timezone(lat, lng),
            country_code=(address.get("country_code") or "").upper() or None,
            country=address.get("country"),
            admin=address.get("state") or address.get("region"),
            precision=_classify_osm_precision(item),
            source=Source.osm,
        )

    def _fallback_timezone(self, lat: float, lng: float) -> str:
        timezone_name = self.timezone_finder.timezone_at(lat=lat, lng=lng)
        if not timezone_name:
            raise ValueError("Timezone could not be resolved for the selected coordinates.")
        return timezone_name
