from app.config import Settings
from app.schemas import Precision, Source
from app.services.geolocation import GeolocationService, _osm_suggestions


def test_fallback_timezone_works_for_known_coordinates() -> None:
    service = GeolocationService(Settings(ENABLE_GOOGLE_PROVIDER=False))
    timezone_name = service._fallback_timezone(28.6139, 77.2090)
    assert timezone_name == "Asia/Kolkata"


def test_service_initializes_without_google() -> None:
    service = GeolocationService(Settings(ENABLE_GOOGLE_PROVIDER=False))
    assert service.settings.google_enabled is False


def test_resolved_place_precision_enum_round_trip() -> None:
    assert Precision.country.value == "country"
    assert Source.osm.value == "osm"


def test_osm_suggestions_prefer_a_city_and_remove_overlapping_admin_records() -> None:
    payload = [
        {
            "osm_type": "relation",
            "osm_id": 1,
            "addresstype": "administrative",
            "importance": 0.7,
            "display_name": "Jabalpur, Madhya Pradesh, 483222, India",
            "address": {"state": "Madhya Pradesh", "country": "India", "country_code": "in"},
        },
        {
            "osm_type": "relation",
            "osm_id": 2,
            "addresstype": "city",
            "importance": 0.8,
            "display_name": "Jabalpur, Ranjhi Tahsil, Madhya Pradesh, India",
            "address": {"city": "Jabalpur", "state": "Madhya Pradesh", "country": "India", "country_code": "in"},
        },
    ]

    suggestions = _osm_suggestions("Jabalpur", payload)

    assert len(suggestions) == 1
    assert suggestions[0].label == "Jabalpur, Madhya Pradesh, India"
    assert suggestions[0].secondary_label == "City match - Madhya Pradesh, India"
    assert suggestions[0].precision is Precision.city
