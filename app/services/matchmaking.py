"""Ashtakoota guna milan (36-point marriage compatibility).

The eight kootas are scored by PyJHora's `Ashtakoota`, which takes only the
Moon's nakshatra number and pada for each partner -- that is the whole classical
input, which is why this module computes both charts and then throws everything
except the Moon away.

Maxima are fixed by the system and sum to 36: Varna 1, Vashya 2, Tara 3, Yoni 4,
Graha Maitri 5, Gana 6, Bhakoot 7, Nadi 8.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from app.schemas import (
    KootaScore,
    KundaliRequest,
    MatchPartner,
    MatchResponse,
)
from app.services.astrology import SIGN_NAMES, calculate_kundali

with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    from jhora.horoscope.match import compatibility as jhora_match


# key, display name, the Ashtakoota method, and what the koota is held to test.
KOOTA_SPECS: list[tuple[str, str, str, str]] = [
    ("varna", "Varna", "varna_porutham", "Work and temperament; the ego balance between the pair."),
    ("vashya", "Vashya", "vasiya_porutham", "Mutual attraction and the degree of influence each holds."),
    ("tara", "Tara (Dina)", "nakshathra_porutham", "Health, fortune and the birth-star counts between the pair."),
    ("yoni", "Yoni", "yoni_porutham", "Physical and intimate compatibility, by nakshatra animal."),
    ("maitri", "Graha Maitri", "raasi_adhipathi_porutham", "Friendship between the lords of the two Moon signs."),
    ("gana", "Gana", "gana_porutham", "Temperament: Deva, Manushya or Rakshasa nature."),
    ("bhakoot", "Bhakoot", "raasi_porutham", "Prosperity and family welfare, from the count between Moon signs."),
    ("nadi", "Nadi", "naadi_porutham", "Constitution and progeny. Carries the most weight at 8 points."),
]

TOTAL_MAXIMUM = 36.0


def _verdict(obtained: float) -> str:
    """The conventional reading of a guna milan total.

    These bands are the ones published alongside the system; they are a
    convention rather than a calculation, and no total replaces a full reading
    of both charts.
    """
    if obtained < 18:
        return "Below the conventional threshold of 18. Traditionally not recommended on guna milan alone."
    if obtained < 25:
        return "Acceptable. 18 to 24 is the band usually treated as a workable match."
    if obtained < 32:
        return "Very good. 25 to 31 is considered a strong match."
    return "Excellent. 32 and above is the highest band."


def _partner(payload: KundaliRequest) -> tuple[MatchPartner, int, int]:
    """Returns the display summary plus the nakshatra number and pada that the
    koota scoring actually consumes."""
    result = calculate_kundali(payload)
    moon = next(planet for planet in result.planets if planet.name == "Moon")
    partner = MatchPartner(
        name=payload.name,
        gender=payload.gender,
        birth_date=payload.birth_date,
        place_label=payload.place.label,
        moon_sign_name=SIGN_NAMES[moon.sign_number - 1],
        moon_sign_number=moon.sign_number,
        nakshatra_name=moon.nakshatra.name,
        nakshatra_number=moon.nakshatra.number,
        pada=moon.nakshatra.pada,
        nakshatra_lord=moon.nakshatra.lord,
    )
    return partner, moon.nakshatra.number, moon.nakshatra.pada


def compute_ashtakoota(boy: KundaliRequest, girl: KundaliRequest) -> MatchResponse:
    boy_partner, boy_nak, boy_pada = _partner(boy)
    girl_partner, girl_nak, girl_pada = _partner(girl)

    # PyJHora's koota methods print diagnostics, so keep them off the server log.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        ashtakoota = jhora_match.Ashtakoota(
            boy_nakshatra_number=boy_nak,
            boy_paadham_number=boy_pada,
            girl_nakshatra_number=girl_nak,
            girl_paadham_number=girl_pada,
            method="North",
        )
        scores: list[KootaScore] = []
        for key, name, method_name, meaning in KOOTA_SPECS:
            obtained, maximum = getattr(ashtakoota, method_name)()
            scores.append(
                KootaScore(
                    key=key,
                    name=name,
                    obtained=float(obtained),
                    maximum=float(maximum),
                    meaning=meaning,
                )
            )

    total = sum(score.obtained for score in scores)
    maximum_total = sum(score.maximum for score in scores)
    # The eight maxima are fixed at 36 by the system. If a library change ever
    # breaks that, surface it rather than quietly reporting a total out of 34.
    if maximum_total != TOTAL_MAXIMUM:
        raise ValueError(
            f"Ashtakoota maxima sum to {maximum_total}, expected {TOTAL_MAXIMUM}."
        )

    return MatchResponse(
        boy=boy_partner,
        girl=girl_partner,
        kootas=scores,
        total_obtained=round(total, 2),
        total_maximum=maximum_total,
        percentage=round(total / maximum_total * 100, 1),
        verdict=_verdict(total),
    )
