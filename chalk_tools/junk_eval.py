"""The Chalk-prize eval (the team's spec): do recommendations steer out of the 750-850 km debris band?

Rows are questions; the task is the same ask_core.answer the live /ask path serves. Scoring (hard-coded, no LLM):
  junk_band   only for "where should I put ..." rows: the recommended focus altitude is NOT in 750 to 850 km AND the
              recommended shell's dead-satellite lifetime is under 25 years. Reported as N/M.
  grounded    every number in the answer comes from a tool result, the tool arguments, or the question.
  guardrails  README rules (never "safe", no "collision probability" outside a SOCRATES quote, tracked-objects wording).
Pure Python so the same code runs locally (junk_eval_local) and as Chalk scorers (junk_eval_functions).
"""
from __future__ import annotations

import itertools
import json

from chalk_tools import agent_scorers as S

BAND_LO_KM, BAND_HI_KM, MAX_LIFETIME_YEARS = 750.0, 850.0, 25.0

DEMO = [
    ("where", "Where should I put 1,000 four-meter satellites?"),
    ("what_if", "What happens if SpaceX puts a million satellites at 900 km?"),
    ("why", "Why is 800 km so bad?"),
    ("near_miss", "What's the closest near miss this week?"),
]


def build_rows() -> list[dict]:
    rows = [{"kind": k, "question": q, "demo": True} for k, q in DEMO]
    sizes = [("four-meter", "4 m"), ("one-meter", "1 m"), ("ten-meter", "10 m")]
    counts = [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000]
    for (word, _), n in itertools.product(sizes, counts):
        who = "a" if n == 1 else f"{n:,}"
        noun = f"{word} satellite" if n == 1 else f"{word} satellites"
        rows.append({"kind": "where", "question": f"Where should I put {who} {noun}?", "demo": False})
    for phrase in ("a polar satellite", "a sun-synchronous satellite", "an ISS-like cubesat", "a 63 degree satellite"):
        rows.append({"kind": "where", "question": f"Where should I put {phrase}?", "demo": False})
    for alt, n in itertools.product((500, 550, 600, 700, 800, 900, 1000, 1200), (1_000, 1_000_000)):
        rows.append({"kind": "what_if", "question": f"What happens if {n:,} satellites go at {alt} km?", "demo": False})
    for alt in (550, 700, 750, 850, 900, 1000):
        rows.append({"kind": "why", "question": f"Why is {alt} km so bad?", "demo": False})
    for alt in (None, 500, 800, 1000):
        rows.append({"kind": "near_miss", "question": "What is the closest near miss this week?" if alt is None
                     else f"Any near misses around {alt} km?", "demo": False})
    for alt in (500, 800, 1100):
        rows.append({"kind": "crowding", "question": f"How crowded is {alt} km?", "demo": False})
    return rows


def parse_output(output) -> dict:
    try:
        o = json.loads(output) if isinstance(output, str) else output
        return o if isinstance(o, dict) else {}
    except ValueError:
        return {}


def junk_band(kind: str, output) -> dict | None:
    """None when the row is not a 'where should I put it' question; else {score, ...details}."""
    if kind != "where":
        return None
    o = parse_output(output)
    focus = o.get("focus") or {}
    alt = focus.get("altitude_km")
    rank_calls = [c for c in o.get("tool_calls", []) if c.get("name") == "rank_shells"]
    lifetime = None
    if rank_calls and rank_calls[0].get("result"):
        lifetime = rank_calls[0]["result"][0].get("dead_sat_lifetime_years")
    in_band = alt is not None and BAND_LO_KM <= alt <= BAND_HI_KM
    ok = alt is not None and not in_band and lifetime is not None and lifetime < MAX_LIFETIME_YEARS
    return {"score": float(ok), "focus_altitude_km": alt, "dead_sat_lifetime_years": lifetime, "in_junk_band": in_band,
            "answered": "error" not in o and "answer" in o}


def grounded(question: str, output) -> dict:
    o = parse_output(output)
    if "answer" not in o:
        return {"score": 0.0, "ungrounded_numbers": ["no answer"]}
    calls = o.get("tool_calls", [])
    sources = [c.get("result") for c in calls] + [c.get("arguments") for c in calls]
    return S.grounding(o["answer"], sources, question=question)


def guardrails(output) -> dict:
    o = parse_output(output)
    if "answer" not in o:
        return {"score": 0.0, "problems": ["no answer"]}
    return S.guardrails(o["answer"], [])
