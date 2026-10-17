"""Tests for the tool-calling cases and the hard-coded agent scorers. No data files, Grok or Chalk needed."""
import json
from collections import Counter

import pytest

from chalk_tools import agent_scorers as S
from chalk_tools.tool_call_cases import CASES


def perfect_calls(case):
    return [{"name": c["tool"], "args": dict(c["args"])} for c in case["expected"]["calls"]]


# ---------- the case list ----------

def test_case_ids_unique_and_groups_cover_the_plan():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    groups = Counter(c["group"] for c in CASES)
    for g in ("shell_crowding", "objects_near", "close_approaches", "recommend_orbit"):
        assert groups[g] >= 6, g
    for g in ("no_call", "out_of_scope", "multi_step", "multi_turn"):
        assert groups[g] >= 1, g


def test_every_expected_call_uses_a_real_tool_and_valid_arguments():
    for c in CASES:
        for e in c["expected"]["calls"]:
            assert e["tool"] in S.SIGNATURES, c["id"]
            sig = S.SIGNATURES[e["tool"]]
            assert set(e["args"]) <= set(sig["required"] + sig["optional"]), c["id"]
            assert all(r in e["args"] for r in sig["required"]), c["id"]
            assert S.check_call({"name": e["tool"], "args": e["args"]}) is None, c["id"]
            assert set(e["tol"]) <= set(e["args"]), c["id"]
        assert c["expected"]["out_of_scope"] <= c["expected"]["no_call"]


# ---------- tool-call scoring ----------

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_a_perfect_agent_scores_one_everywhere(case):
    s = S.score_tool_calls(case, perfect_calls(case))
    assert s == {"selection": 1.0, "args": 1.0, "budget": 1.0, "valid": 1.0, "overall": 1.0}, s


def case_by_id(i):
    return next(c for c in CASES if c["id"] == i)


def test_wrong_tool_fails_selection():
    c = case_by_id("sc1")
    s = S.score_tool_calls(c, [{"name": "objects_near", "args": {"altitude_km": 550, "inclination_deg": 53}}])
    assert s["selection"] == 0.0 and s["overall"] == 0.0


def test_argument_tolerance_and_unit_conversion():
    c = case_by_id("sc4")  # 300 miles = 483 km, tolerance 25
    assert S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 300}}])["args"] == 0.0  # forgot to convert
    assert S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 500}}])["args"] == 1.0
    assert S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": "490"}}])["args"] == 1.0  # numeric string ok


def test_mission_phrases_check_the_inclination():
    c = case_by_id("ro2")  # sun-synchronous = 98 +/- 1.5
    assert S.score_tool_calls(c, [{"name": "recommend_orbit", "args": {"inclination_deg": 98.5}}])["args"] == 1.0
    assert S.score_tool_calls(c, [{"name": "recommend_orbit", "args": {"inclination_deg": 90}}])["args"] == 0.0


def test_extra_default_arguments_are_not_penalized_but_invalid_ones_are():
    c = case_by_id("sc1")
    ok = S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 550, "inclination_deg": None}}])
    assert ok["overall"] == 1.0
    bad = S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 35786}}])
    assert bad["valid"] == 0.0 and bad["overall"] == 0.0


def test_no_call_and_out_of_scope_rows():
    assert S.score_tool_calls(case_by_id("nc1"), [])["overall"] == 1.0
    assert S.score_tool_calls(case_by_id("nc1"), [{"name": "shell_crowding", "args": {"altitude_km": 500}}])["overall"] == 0.0
    # calling a tool for geostationary is both a wrong call and an invalid one
    s = S.score_tool_calls(case_by_id("os1"), [{"name": "shell_crowding", "args": {"altitude_km": 35786}}])
    assert s["selection"] == 0.0 and s["valid"] == 0.0


def test_multi_step_order_does_not_matter_and_missing_second_call_fails():
    c = case_by_id("ms1")
    calls = perfect_calls(c)[::-1]
    assert S.score_tool_calls(c, calls)["overall"] == 1.0
    assert S.score_tool_calls(c, calls[:1])["selection"] == 0.0


def test_budget_catches_runaway_calls():
    c = case_by_id("sc1")
    many = [{"name": "shell_crowding", "args": {"altitude_km": 550}}] * 4
    s = S.score_tool_calls(c, many)
    assert s["budget"] == 0.0 and s["selection"] == 0.0


def test_multi_turn_relative_phrase_resolves_against_context():
    c = case_by_id("mt1")  # context 550, "a bit higher" = 600
    assert S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 600}}])["overall"] == 1.0
    assert S.score_tool_calls(c, [{"name": "shell_crowding", "args": {"altitude_km": 50}}])["valid"] == 0.0  # sent "+50" as absolute


@pytest.mark.parametrize("call,reason", [
    ({"name": "nope", "args": {}}, "unknown tool"),
    ({"name": "shell_crowding", "args": {}}, "missing altitude_km"),
    ({"name": "shell_crowding", "args": {"altitude_km": 550, "foo": 1}}, "unknown argument"),
    ({"name": "objects_near", "args": {"altitude_km": 550, "inclination_deg": 200}}, "out of range"),
    ({"name": "close_approaches", "args": {"min_altitude_km": 600, "max_altitude_km": 500}}, "below"),
    ({"name": "recommend_orbit", "args": {"inclination_deg": 53, "top_n": 2.5}}, "whole"),
    ({"name": "shell_crowding", "args": {"altitude_km": True}}, "out of range"),
])
def test_check_call_rejects_bad_calls(call, reason):
    assert reason in S.check_call(call)


# ---------- grounding ----------

RES = {"ok": True, "data": {"shell_km": [550, 600], "total": 1309, "counts": {"PAY": 1036, "DEB": 216, "R/B": 51, "UNK": 6},
                            "approaches": [{"miss_distance_m": 8.0, "miss_distance_km_hint": 0.008}]}}


def test_grounding_accepts_numbers_from_tools_with_formatting_and_conversion():
    ans = "The 550 to 600 km shell holds 1,309 tracked objects, including 216 debris pieces, and the closest approach is 8 meters."
    assert S.grounding(ans, [RES], question="How crowded is 550 km?")["score"] == 1.0
    assert S.grounding("That is about 0.008 kilometers.", [RES])["score"] == 1.0  # m to km


def test_grounding_flags_invented_numbers():
    g = S.grounding("The shell holds 1,500 tracked objects.", [RES])
    assert g["score"] == 0.0 and 1500.0 in g["ungrounded_numbers"]


def test_grounding_allows_numbers_the_user_or_globe_supplied():
    assert S.grounding("At 480 km you are alone.", [], question="is 480 km busy?")["score"] == 1.0
    assert S.grounding("At 480 km you are alone.", [], context={"altitude_km": 480})["score"] == 1.0
    assert S.grounding("At 480 km you are alone.", [])["score"] == 0.0


# ---------- guardrails ----------

def test_guardrails_never_safe_unless_negated():
    assert S.guardrails("This shell is safe for your satellite.", [RES])["score"] == 0.0
    assert S.guardrails("Quiet does not mean safe; 1,309 tracked objects are here.", [RES])["score"] == 1.0
    assert S.guardrails("That is the safest shell.", [RES])["score"] == 0.0


def test_guardrails_collision_probability_only_when_quoting_socrates():
    assert S.guardrails("The collision probability is high.", [RES])["score"] == 0.0
    ok = S.guardrails("SOCRATES lists a collision probability of 0.01 for these tracked objects.", [RES])
    assert ok["score"] == 1.0, ok


def test_guardrails_empty_region_and_tracked_wording():
    empty = {"ok": True, "data": {"total": 0, "counts": {}}}
    assert S.guardrails("Nothing is there.", [empty])["score"] == 0.0
    assert S.guardrails("There are no tracked objects in that shell.", [empty])["score"] == 1.0
    assert S.guardrails("The shell holds 1,309 objects.", [RES])["score"] == 0.0  # does not say tracked
    assert S.guardrails("The shell holds 1,309 tracked objects.", [RES])["score"] == 1.0


# ---------- output shape ----------

def test_json_valid():
    assert S.json_valid(json.dumps({"answer": "x", "tool_calls": [{"name": "shell_crowding", "args": {"altitude_km": 550}}]}))["score"] == 1.0
    assert S.json_valid({"answer": "x", "tool_calls": []})["score"] == 1.0
    assert S.json_valid("not json")["score"] == 0.0
    assert S.json_valid({"answer": 3, "tool_calls": []})["score"] == 0.0
    assert S.json_valid({"answer": "x", "tool_calls": [{"args": {}}]})["score"] == 0.0
