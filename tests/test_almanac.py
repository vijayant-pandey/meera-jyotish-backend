from datetime import date

import pytest

from app.services import almanac, jhora_gateway as gateway

ON = date(2026, 10, 4)


@pytest.fixture(scope="module")
def place():
    offset = gateway.utc_offset_hours("Asia/Kolkata", ON)
    return gateway.place_of(23.170152, 79.932451, offset, "Jabalpur")


@pytest.fixture(scope="module")
def jd():
    return gateway.julian_day(ON)


def test_the_swisseph_shim_is_installed() -> None:
    # PyJHora unpacks calc_ut as a 2-tuple; the installed pyswisseph returns 3.
    # Without the shim every position-computing PyJHora feature raises
    # "too many values to unpack".
    assert gateway.PATCHED_MODULE_COUNT > 0


def test_the_shim_does_not_change_what_this_app_sees() -> None:
    # The shim is scoped to jhora modules. This app's own calls must still get
    # the real 3-tuple, or every chart it casts would break.
    import swisseph as swe

    result = swe.calc_ut(gateway.julian_day(ON), swe.SUN, swe.FLG_SWIEPH)
    assert len(result) == 3


def test_jhora_context_restores_lahiri() -> None:
    # PyJHora defaults to TRUE_PUSHYA; leaving that set would silently shift
    # every subsequent chart this app casts by about 1 degree 08 minutes.
    import swisseph as swe

    with gateway.jhora_context():
        pass
    before = swe.get_ayanamsa_ut(gateway.julian_day(ON))
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    assert before == pytest.approx(swe.get_ayanamsa_ut(gateway.julian_day(ON)), abs=1e-9)


@pytest.mark.parametrize("section", sorted(almanac.SECTIONS))
def test_every_section_returns_the_shared_shape(section, place, jd) -> None:
    builder = almanac.SECTIONS[section]
    if section in almanac.NATIVE_SECTIONS:
        result = builder(23.170152, 79.932451, "Asia/Kolkata", ON)
    elif section == "festivals":
        result = builder(place, jd, ON, 2)
    else:
        result = builder(place, jd, ON)

    assert result["title"]
    assert result["columns"], f"{section} declares no columns"
    # Two reserved keys are never rendered as columns: "group" splits a section
    # into day/night tables, and "tone" drives the row colour.
    keys = {column["key"] for column in result["columns"]} | {"group", "tone"}
    for row in result["rows"]:
        assert keys.issuperset(row.keys()), f"{section} row has undeclared keys"


def test_tone_is_a_closed_set_so_the_page_can_colour_from_it() -> None:
    # The page paints green/red/blue off this value, so an unexpected tone would
    # silently render as an uncoloured row.
    allowed = {"good", "bad", "neutral"}
    hora = almanac.hora(23.170152, 79.932451, "Asia/Kolkata", ON)
    chaughadiya = almanac.chaughadiya(23.170152, 79.932451, "Asia/Kolkata", ON)

    for result in (hora, chaughadiya):
        tones = {row["tone"] for row in result["rows"]}
        assert tones <= allowed
        # All three are actually used, rather than collapsing to good/bad.
        assert tones == allowed


def test_the_benefics_and_malefics_are_split_three_ways() -> None:
    rows = almanac.hora(23.170152, 79.932451, "Asia/Kolkata", ON)["rows"]
    tone_of = {row["lord"]: row["tone"] for row in rows}

    assert tone_of["Jupiter"] == tone_of["Venus"] == "good"
    assert tone_of["Sun"] == tone_of["Mars"] == tone_of["Saturn"] == "bad"
    # Mercury and the Moon are conditional benefics, not forced either way.
    assert tone_of["Mercury"] == tone_of["Moon"] == "neutral"


def test_hora_and_chaughadiya_split_day_and_night() -> None:
    hora = almanac.hora(23.170152, 79.932451, "Asia/Kolkata", ON)
    chaughadiya = almanac.chaughadiya(23.170152, 79.932451, "Asia/Kolkata", ON)

    # Twelve horas each side, eight choghadiya each side.
    for result, per_side, groups in (
        (hora, 12, ("Day Hora", "Night Hora")),
        (chaughadiya, 8, ("Day Choghadiya", "Night Choghadiya")),
    ):
        counts: dict[str, int] = {}
        for row in result["rows"]:
            counts[row["group"]] = counts.get(row["group"], 0) + 1
        assert set(counts) == set(groups)
        assert all(count == per_side for count in counts.values())


def test_hora_starts_with_the_weekday_lord() -> None:
    # 2026-10-04 is a Sunday, so the first day hora is the Sun's.
    result = almanac.hora(23.170152, 79.932451, "Asia/Kolkata", ON)
    first = result["rows"][0]

    assert first["group"] == "Day Hora"
    assert first["lord"] == "Sun"
    assert first["quality"] == "Vigorous"


def test_chaughadiya_marks_only_the_three_avoided_names() -> None:
    result = almanac.chaughadiya(23.170152, 79.932451, "Asia/Kolkata", ON)
    bad = {row["name"] for row in result["rows"] if row["quality"] == "Inauspicious"}

    assert bad == {"Udvega", "Kala", "Roga"}


def test_muhurta_marks_the_avoided_periods() -> None:
    rows = {
        row["name"]: row
        for row in almanac.muhurta(23.170152, 79.932451, "Asia/Kolkata", ON)["rows"]
    }

    for name in ("Rahu Kalam", "Yamaganda", "Gulika Kalam"):
        assert rows[name]["quality"] == "Inauspicious"
    assert rows["Abhijit Muhurta"]["quality"] == "Auspicious"


def test_the_two_rahu_kalam_figures_agree() -> None:
    # The muhurta table and the dedicated Rahu Kaal page showed different
    # windows on the same screen, because the table took its trikalam from
    # PyJHora while the page used the published weekday rule. Both now use the
    # rule, and this pins them together.
    from app.services.day_tables import rahu_kaal

    table = {
        row["name"]: row
        for row in almanac.muhurta(23.170152, 79.932451, "Asia/Kolkata", ON)["rows"]
    }["Rahu Kalam"]
    page = rahu_kaal(23.170152, 79.932451, "Asia/Kolkata", ON)

    assert table["start"] == page["start"][11:16]
    assert table["end"] == page["end"][11:16]


def test_rahu_kaal_follows_the_published_weekday_periods() -> None:
    # Monday the 2nd period, Saturday the 3rd, Friday the 4th, Wednesday the
    # 5th, Thursday the 6th, Tuesday the 7th, Sunday the 8th.
    from app.services.day_tables import RAHU_PERIOD_BY_WEEKDAY, rahu_kaal

    assert RAHU_PERIOD_BY_WEEKDAY == {
        "Sunday": 8, "Monday": 2, "Tuesday": 7, "Wednesday": 5,
        "Thursday": 6, "Friday": 4, "Saturday": 3,
    }
    # No weekday puts Rahu in the first period, which is why it is held free.
    assert 1 not in RAHU_PERIOD_BY_WEEKDAY.values()

    result = rahu_kaal(23.170152, 79.932451, "Asia/Kolkata", ON)
    assert result["weekday"] == "Sunday"
    assert result["period"] == 8
    # The eighth period ends at sunset.
    assert result["end"][11:16] == result["sunset"][11:16]


def test_retrogrades_always_call_the_nodes_vakri(place, jd) -> None:
    # Rahu and Ketu are retrograde by definition. PyJHora does not always list
    # Ketu, so the table must assert it rather than echo the library.
    rows = {row["planet"]: row["motion"] for row in almanac.retrogrades(place, jd, ON)["rows"]}

    assert "Vakri" in rows["Rahu"]
    assert "Vakri" in rows["Ketu"]
    assert "Sun" not in rows and "Moon" not in rows


def test_festivals_are_computed_not_listed(place, jd) -> None:
    result = almanac.festivals(place, jd, ON, 2)

    assert len(result["rows"]) > 10
    for row in result["rows"]:
        assert row["date"] >= ON.isoformat()
    # Sorted by date, so the page can render them straight through.
    assert result["rows"] == sorted(result["rows"], key=lambda r: (r["date"], r["name"]))


def test_doshas_take_their_verdict_from_the_structured_functions(place) -> None:
    # PyJHora's get_dosha_details() returns definitional prose: for Manglik and
    # Pitru it never states presence at all, so deciding from the text gives
    # false positives. The verdict must come from the boolean functions.
    offset = gateway.utc_offset_hours("Asia/Kolkata", date(1990, 12, 2))
    birth_place = gateway.place_of(23.170152, 79.932451, offset, "Jabalpur")
    jd = gateway.julian_day(date(1990, 12, 2)) + (12 + 50 / 60) / 24 - offset / 24

    rows = {row["name"]: row for row in almanac.doshas(jd, birth_place)["rows"]}

    assert len(rows) == 8
    assert "Manglik Dosha" in rows
    assert "Ganda Moola Dosha" in rows
    for row in rows.values():
        assert row["present"] in {"Present", "Not present", "Not determined"}
