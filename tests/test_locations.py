"""Geographic slots: an orbit over China or Africa has to actually reach that latitude."""
import math

import pytest

from chalk_tools import agent_scorers as scorers
from pipeline import locations as L


def _unit(inclination_deg, raan, lat_deg):
    """Ascending-pass position in the globe frame, same equations as web/src/place.ts."""
    inc = math.radians(inclination_deg)
    lon_u = math.asin(max(-1.0, min(1.0, math.sin(math.radians(lat_deg)) / math.sin(inc))))
    o = math.radians(raan)
    c, s = math.cos(lon_u), math.sin(lon_u)
    ci = math.cos(inc)
    x_orb = c * math.cos(o) - s * ci * math.sin(o)
    y_orb = c * math.sin(o) + s * ci * math.cos(o)
    z_orb = s * math.sin(inc)
    return (y_orb, z_orb, x_orb)


def _expected(lat_deg, lon_deg):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    return (
        math.cos(lat) * math.sin(lon),
        math.sin(lat),
        math.cos(lat) * math.cos(lon),
    )


def test_china_requires_an_inclination_that_reaches_54_degrees():
    result = L.rank_over("china", 525, top=8)
    assert result["region"]["min_reach_deg"] == 54
    for row in result["rows"]:
        assert L.covers(row["inclination_deg"], 54)
        assert 500 <= row["altitude_km"] < 550 or row["alt_lo"] == 500
        assert row["alt_lo"] == 500 and row["alt_hi"] == 550
    best = result["rows"][0]
    assert best["debris"] == min(row["debris"] for row in result["rows"])
    assert best["debris"] <= result["busiest"]["debris"]
    # 53° clips the south of China and misses the north. It must not win.
    assert best["inclination_deg"] >= 54
    assert all(row["inclination_deg"] >= 54 for row in result["rows"])


def test_africa_at_800_km_stays_in_that_shell_and_reaches_the_continent():
    result = L.rank_over("Africa", 800, top=5)
    assert result["region"]["id"] == "africa"
    assert result["region"]["min_reach_deg"] == 37
    for row in result["rows"]:
        assert row["alt_lo"] == 800 and row["alt_hi"] == 850
        assert row["altitude_km"] == 800
        assert L.covers(row["inclination_deg"], 37)
        assert abs(row["latitude_deg"]) <= row["reaches_deg"] + 1e-6
    debris = [row["debris"] for row in result["rows"]]
    assert debris == sorted(debris)


def test_without_an_altitude_the_quietest_covering_shell_from_500_km_wins():
    result = L.rank_over("over china")
    best = result["rows"][0]
    assert best["alt_lo"] >= 500
    assert L.covers(best["inclination_deg"], 54)
    # The list is the comparison inside that shell, not the same band repeated.
    assert {row["alt_lo"] for row in result["rows"]} == {best["alt_lo"]}
    assert len({row["inc_lo"] for row in result["rows"]}) == len(result["rows"])
    assert result["busiest"]["alt_lo"] == best["alt_lo"]
    assert result["busiest"]["debris"] > best["debris"]
    # Same shell, nothing covering China has fewer debris or fewer objects.
    same = L.rank_over("china", best["altitude_km"], top=12)["rows"]
    assert (best["debris"], best["total"]) <= (same[0]["debris"], same[0]["total"])


def test_a_partial_band_names_the_slice_that_reaches():
    result = L.rank_over("china", 800, top=5)
    top = result["rows"][0]
    assert top["band_covers"] is False
    assert top["covering_lo"] == 120
    assert top["covering_hi"] == 126
    assert top["covering_lo"] >= top["inc_lo"]
    assert top["covering_hi"] <= top["inc_hi"]
    full = L.rank_over("china", 525, top=1)["rows"][0]
    assert full["band_covers"] is True
    text = L.explain(result)
    assert "120 to 126" in text
    grounded = scorers.grounding(text, [result], question="over China at 800 km")
    assert grounded["score"] == 1.0, grounded
    assert len(text.split(". ")) <= 6


def test_equatorial_orbit_does_not_cover_china_or_africa():
    assert not L.covers(0, 54)
    assert not L.covers(0, 37)
    assert L.covering_inclination(0, 10, 54) is None
    assert L.covers(98, 54)
    assert L.covers(115, 37)


def test_unknown_place_lists_the_ones_we_know():
    with pytest.raises(ValueError, match="China"):
        L.rank_over("antarctica")


def test_raan_puts_the_ascending_pass_over_the_place():
    cases = [(115, 35, 104), (98, 9, 20), (60, 50, 10), (40, -25, 134)]
    for inc, lat, lon in cases:
        raan = L.raan_deg(inc, lat, lon)
        got = _unit(inc, raan, lat)
        want = _expected(lat, lon)
        # raan_deg is rounded to 0.01°, about a kilometer on the ground.
        assert got == pytest.approx(want, abs=1e-4)


def test_spoken_answer_uses_only_numbers_from_the_result():
    for question, alt in (("where can I put a satellite over Africa", None), ("over China at 800 km", 800)):
        region = L.find_region(question)
        result = L.rank_over(region.id, alt if alt is not None else L.mentioned_altitude_km(question))
        text = L.explain(result)
        assert "tracked" in text.lower()
        assert scorers.SAFE.search(text) is None
        grounded = scorers.grounding(text, [result], question=question)
        assert grounded["score"] == 1.0, grounded
        assert len(text.split(". ")) <= 6


def test_ask_sends_over_china_to_an_orbit_that_reaches_it():
    from api.agent import ask_without_grok
    from chalk_tools import ask_core

    parsed = ask_core.parse_question("Where can I put a satellite over China?")
    assert parsed["intent"] == "locate" and parsed["region"] == "china"
    plain = ask_core.parse_question("Where should I put 1,000 four-meter satellites?")
    assert plain["intent"] == "rank" and plain["region"] is None

    body = ask_core.answer("Where can I put a satellite over Africa at 800 km?")
    assert body["focus"]["place"] == "Africa"
    assert body["focus"]["altitude_km"] == 800
    assert L.covers(body["focus"]["inclination_deg"], 37)
    grounded = scorers.grounding(
        body["answer"],
        [call["result"] for call in body["tool_calls"]],
        question="Where can I put a satellite over Africa at 800 km?",
    )
    assert grounded["score"] == 1.0, grounded

    local = ask_without_grok("Where can I put a satellite over China at 525 km?")
    assert local["reasoner"] == "local"
    assert local["focus"]["place"] == "China"
    assert local["focus"]["altitude_km"] == 525
    assert L.covers(local["focus"]["inclination_deg"], 54)
    assert any(event.get("latitude_deg") == 35 for event in local["ui_events"])


def test_place_names_parse_without_stealing_a_plain_where_question():
    assert L.find_region("Where can I put a satellite over Africa?").id == "africa"
    assert L.find_region("over China at 800 km").id == "china"
    assert L.find_region("put one over the United States").id == "united states"
    assert L.find_region("Where should I put 1,000 four-meter satellites?") is None
    assert L.mentioned_altitude_km("over China at 800 km") == 800
    assert L.mentioned_altitude_km("over Africa") is None
