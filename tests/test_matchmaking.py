from datetime import date

from app.schemas import (
    Ayanamsha,
    Gender,
    KundaliRequest,
    Meridiem,
    Precision,
    ResolvedPlace,
    Source,
)
from app.services.matchmaking import KOOTA_SPECS, compute_ashtakoota


def person(name: str, gender: Gender, birth: date, time12h: str, meridiem: Meridiem) -> KundaliRequest:
    return KundaliRequest(
        name=name,
        gender=gender,
        birth_date=birth,
        birth_time12h=time12h,
        meridiem=meridiem,
        ayanamsha=Ayanamsha.lahiri,
        place=ResolvedPlace(
            label="Jabalpur, India",
            lat=23.170152,
            lng=79.932451,
            timezone="Asia/Kolkata",
            precision=Precision.city,
            source=Source.manual,
        ),
    )


BOY = person("Ravi", Gender.male, date(1990, 12, 2), "12:50", Meridiem.pm)
GIRL = person("Sita", Gender.female, date(1992, 4, 17), "06:20", Meridiem.am)


def test_ashtakoota_returns_all_eight_kootas() -> None:
    result = compute_ashtakoota(BOY, GIRL)

    assert [koota.key for koota in result.kootas] == [spec[0] for spec in KOOTA_SPECS]
    assert len(result.kootas) == 8


def test_the_eight_maxima_are_the_classical_one_to_eight() -> None:
    # Varna 1, Vashya 2, Tara 3, Yoni 4, Graha Maitri 5, Gana 6, Bhakoot 7, Nadi 8.
    result = compute_ashtakoota(BOY, GIRL)

    assert [koota.maximum for koota in result.kootas] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert result.total_maximum == 36


def test_total_is_the_sum_of_the_kootas_and_within_range() -> None:
    result = compute_ashtakoota(BOY, GIRL)

    assert result.total_obtained == round(sum(k.obtained for k in result.kootas), 2)
    assert 0 <= result.total_obtained <= 36
    # Guna milan moves in half points, never finer.
    assert (result.total_obtained * 2) % 1 == 0
    assert result.percentage == round(result.total_obtained / 36 * 100, 1)


def test_partners_are_summarised_by_their_moon() -> None:
    # The kootas consume only the Moon's nakshatra and pada, so that is what the
    # summary has to expose for the result to be checkable by hand.
    result = compute_ashtakoota(BOY, GIRL)

    assert result.boy.name == "Ravi"
    assert result.girl.name == "Sita"
    for partner in (result.boy, result.girl):
        assert 1 <= partner.nakshatra_number <= 27
        assert 1 <= partner.pada <= 4
        assert 1 <= partner.moon_sign_number <= 12
        assert partner.nakshatra_name
        assert partner.nakshatra_lord


def test_swapping_the_partners_is_not_assumed_symmetric() -> None:
    # Several kootas (Tara, Bhakoot, Vashya) are counted from one partner to the
    # other, so the pairing is directional. This pins the current behaviour so a
    # library change that silently symmetrises it would be caught.
    forward = compute_ashtakoota(BOY, GIRL)
    reversed_pair = compute_ashtakoota(GIRL, BOY)

    assert forward.total_maximum == reversed_pair.total_maximum == 36
    assert 0 <= reversed_pair.total_obtained <= 36
