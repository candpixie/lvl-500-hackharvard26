"""Tests for the Chalk ask reasoner. Uses the committed data/out files; no network, Chalk or Grok."""
import json
import math

import pytest

from chalk_tools import agent_scorers as S
from chalk_tools import ask_core as A

pytestmark = pytest.mark.skipif(
    not (A.LOCAL_ROOT / "data/out/shells.json").exists() or not (A.LOCAL_ROOT / "data/out/tools/catalog.csv.gz").exists(),
    reason="needs data/out/shells.json and data/out/tools (pipeline/build_tools_data.py)")

DEMO = [
    "Where should I put 1,000 four-meter satellites?",
    "What happens if SpaceX puts a million satellites at 900 km?",
    "Why is 800 km so bad?",
    "What's the closest near miss this week?",
]


@pytest.mark.parametrize("q,expect", [
    ("Where should I put 1,000 four-meter satellites?", {"intent": "rank", "count": 1000, "dims_m": [4.0, 2.0, 1.0], "alt_km": None}),
    ("What happens if SpaceX puts a million satellites at 900 km?", {"intent": "place", "count": 1_000_000, "alt_km": 900.0}),
    ("Why is 800 km so bad?", {"intent": "why", "alt_km": 800.0}),
    ("What's the closest near miss this week?", {"intent": "near_miss", "alt_km": None}),
    ("any near misses around 800 km", {"intent": "near_miss", "alt_km": 800.0}),
    ("How crowded is 550 km?", {"intent": "crowding", "alt_km": 550.0}),
    ("What if I put 5,000 satellites at 700 km?", {"intent": "place", "count": 5000, "alt_km": 700.0}),
    ("Where should one cubesat go for a polar orbit?", {"intent": "rank", "count": 1, "inc_deg": 90.0}),
    ("what is the best place to put 1 satellite. show me the highest rating", {"intent": "rank", "count": 1}),
    ("Where should I put 2.5 million 6 meter satellites in a sun-synchronous orbit", {"intent": "rank", "count": 2_500_000, "inc_deg": 98.0, "dims_m": [6.0, 3.0, 1.5]}),
    ("what is the weather", {"intent": None}),
])
def test_parse_question(q, expect):
    p = A.parse_question(q)
    for k, v in expect.items():
        assert p[k] == v, (q, k, p)


def test_demo_questions_match_the_documented_answers():
    r1 = A.answer(DEMO[0])
    assert r1["focus"]["altitude_km"] == 525 and [c["name"] for c in r1["tool_calls"]] == ["rank_shells"]
    assert r1["focus"]["count"] == 1000 and r1["focus"]["dims_m"] == [4.0, 2.0, 1.0]
    assert [row["alt_lo"] for row in r1["tool_calls"][0]["result"]] == [500, 550, 600]  # docs: safest 500/550/600
    r2 = A.answer(DEMO[1])
    score_900 = r2["tool_calls"][0]["result"]["score"]
    assert 41 <= score_900 <= 43 and r2["focus"]["altitude_km"] == 900  # docs: about 42
    r3 = A.answer(DEMO[2])
    assert r3["focus"]["altitude_km"] == 825 and r3["tool_calls"][0]["result"]["DEB"] > r3["tool_calls"][0]["result"]["PAY"]
    r4 = A.answer(DEMO[3])
    assert "NUSAT-47" in r4["answer"] and "12 meters" in r4["answer"]  # docs: NuSat-47 vs Fengyun-1C, 12 m


def test_million_satellites_at_550_scores_about_78():
    assert 77 <= A.resolvers().scoring.place(550, 53, [4, 2, 1], 1_000_000)["score"] <= 79


@pytest.mark.parametrize("q", DEMO + ["How crowded is 550 km?", "any near misses around 800 km", "What if I put one satellite at 600 km?"])
def test_answers_follow_the_house_rules(q):
    r = A.answer(q)
    assert set(r) >= {"answer", "focus", "tool_calls", "note"} and r["note"] == "tracked objects only, lower bound"
    # numbers may come from tool results or from the arguments the answer states back (size, count, altitude)
    results = [c["result"] for c in r["tool_calls"]] + [c["arguments"] for c in r["tool_calls"]]
    assert S.guardrails(r["answer"], [])["score"] == 1.0, S.guardrails(r["answer"], [])
    g = S.grounding(r["answer"], results, question=q)
    assert g["score"] == 1.0, g  # every spoken number comes from a tool result or the question
    assert "lower bound" in r["answer"].lower() or "no predicted" in r["answer"].lower() or "lists no" in r["answer"].lower()
    assert len(r["answer"].split(". ")) <= 6  # short enough to speak
    json.dumps(r)


def test_one_satellite_focus_carries_count():
    r = A.answer("what is the best place to put 1 satellite. show me the highest rating")
    assert r["focus"]["count"] == 1 and r["focus"]["altitude_km"] == 525


def test_focus_is_valid_whenever_a_shell_is_recommended():
    for q in DEMO + ["How crowded is 550 km?"]:
        f = A.answer(q)["focus"]
        assert f and 200 <= f["altitude_km"] < 2000 and 0 <= f["inclination_deg"] <= 180


def test_near_miss_at_an_altitude_uses_only_nearby_pairs():
    r = A.answer("any near misses around 800 km")
    for row in r["tool_calls"][0]["result"]:
        assert abs(row["mean_alt_km"] - 800) <= A.BAND_KM


def test_unknown_questions_return_an_error_so_grok_falls_back():
    r = A.answer("what is the weather")
    assert "error" in r and "answer" not in r


def test_out_of_range_altitude_is_an_error_not_a_crash():
    with pytest.raises(ValueError):
        A.answer("Why is 5000 km so bad?")


# ---------- the HTTP wrapper (needs flask) ----------

def _client():
    flask = pytest.importorskip("flask")
    from chalk_tools import ask_app
    return ask_app.app.test_client()


def test_http_ask_returns_the_contract_shape():
    r = _client().post("/ask", json={"question": DEMO[0]})
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) >= {"answer", "focus", "tool_calls", "note", "source", "snapshot"} and body["source"] == "chalk"
    assert body["focus"]["altitude_km"] == 525


def test_http_errors_trigger_the_clients_fallback():
    c = _client()
    assert c.post("/ask", json={"question": "what is the weather"}).status_code == 422
    assert c.post("/ask", json={"question": "Why is 5000 km so bad?"}).status_code == 422
    assert c.post("/ask", json={}).status_code == 400
    assert c.post("/ask", data="not json", content_type="text/plain").status_code == 400
    assert c.post("/ask", json={"question": "x" * 601}).status_code == 400
    assert c.get("/ask").status_code == 405  # the client's health probe counts 405 as up
    assert c.get("/health").get_json()["ok"] is True
