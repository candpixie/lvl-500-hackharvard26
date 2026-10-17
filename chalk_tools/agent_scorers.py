"""Hard-coded scorers for the agent's output. Plain Python, no LLM, no Chalk imports, so they are tested locally
and can be wrapped as Chalk eval scorers once agent/run_agent exists.

Agent output shape (docs/api.md): {"answer": str, "tool_calls": [{"name": str, "args": dict, "result": dict}], ...}
Every score is 0.0 to 1.0.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter

SIGNATURES = {
    "shell_crowding": {"required": ["altitude_km"], "optional": ["inclination_deg"]},
    "objects_near": {"required": ["altitude_km", "inclination_deg"], "optional": ["limit"]},
    "close_approaches": {"required": ["min_altitude_km", "max_altitude_km"], "optional": ["limit"]},
    "recommend_orbit": {"required": ["inclination_deg"],
                        "optional": ["min_altitude_km", "max_altitude_km", "top_n", "inclination_band_deg"]},
}
RANGES = {"altitude": (200, 2000), "inclination": (0, 180), "limit": (1, 50), "top_n": (1, 10), "band": (0, 90)}


def _kind(arg: str) -> str:
    if "altitude" in arg:
        return "altitude"
    if "band" in arg:
        return "band"
    return {"limit": "limit", "top_n": "top_n"}.get(arg, "inclination")


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def default_tol(arg: str) -> float:
    return {"altitude": 25.0, "inclination": 2.0, "limit": 0.0, "top_n": 0.0, "band": 0.0}[_kind(arg)]


# ---------- tool selection, arguments, validity, budget ----------

def check_call(call: dict) -> str | None:
    """None if the call is valid, else the reason it is not (unknown tool, missing/unknown/out-of-range argument)."""
    sig = SIGNATURES.get(call.get("name"))
    if sig is None:
        return f"unknown tool {call.get('name')!r}"
    args = call.get("args") or {}
    for r in sig["required"]:
        if args.get(r) is None:
            return f"missing {r}"
    for k, v in args.items():
        if k not in sig["required"] + sig["optional"]:
            return f"unknown argument {k}"
        if v is None and k in sig["optional"]:
            continue
        x = _num(v)
        lo, hi = RANGES[_kind(k)]
        if x is None or not (lo <= x < hi if _kind(k) == "altitude" else lo <= x <= hi):
            return f"{k}={v!r} out of range"
        if _kind(k) in ("limit", "top_n") and x != int(x):
            return f"{k} must be whole"
    if "min_altitude_km" in args and "max_altitude_km" in args and args["min_altitude_km"] is not None and args["max_altitude_km"] is not None:
        if _num(args["min_altitude_km"]) >= _num(args["max_altitude_km"]):
            return "min_altitude_km must be below max_altitude_km"
    return None


def _arg_score(expected: dict, actual_args: dict) -> float:
    exp_args = expected["args"]
    if not exp_args:
        return 1.0
    ok = 0
    for k, v in exp_args.items():
        a = _num(actual_args.get(k))
        tol = expected.get("tol", {}).get(k, default_tol(k))
        if a is not None and abs(a - float(v)) <= tol + 1e-9:
            ok += 1
    return ok / len(exp_args)


def score_tool_calls(case: dict, tool_calls: list[dict]) -> dict:
    """selection (right set of tools), args (expected arguments within tolerance), valid (every call legal),
    budget (no more than one extra call), plus the weakest of them as 'overall'."""
    exp = case["expected"]
    calls = [{"name": c.get("name"), "args": c.get("args") or {}} for c in (tool_calls or [])]
    exp_calls = exp["calls"]
    if exp["no_call"]:
        none = not calls
        s = {"selection": float(none), "args": float(none), "budget": float(none)}
    else:
        selection = float(Counter(c["name"] for c in calls) == Counter(e["tool"] for e in exp_calls))
        used, scores = set(), []
        for e in exp_calls:
            best, best_i = 0.0, None
            for i, c in enumerate(calls):
                if i not in used and c["name"] == e["tool"]:
                    sc = _arg_score(e, c["args"])
                    if best_i is None or sc > best:
                        best, best_i = sc, i
            if best_i is not None:
                used.add(best_i)
            scores.append(best)
        s = {"selection": selection, "args": sum(scores) / len(scores), "budget": float(len(calls) <= len(exp_calls) + 1)}
    s["valid"] = float(all(check_call(c) is None for c in calls))
    s["overall"] = min(s.values())
    return s


# ---------- answer text: grounding, guardrails ----------

NUM = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")
GROUND_CONSTANTS = {50, 200, 2000}  # fixed facts of the view: shell width and covered range


def _numbers_in(text: str) -> set[float]:
    out = set()
    for m in NUM.findall(text or ""):
        try:
            out.add(float(m.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def _walk_numbers(obj, acc: set[float]):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if not (isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj))):
            acc.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, acc)
    elif isinstance(obj, str):
        acc |= _numbers_in(obj)


def _allowed(x: float, source: set[float]) -> bool:
    """x matches a source number directly or after the conversions an answer may reasonably apply."""
    for s in source:
        for candidate in (s, s * 1000, s / 1000, s * 100, round(s), round(s, 1), round(s, 2), round(s * 100), round(s * 100, 1), math.floor(s), math.ceil(s)):
            if abs(x - candidate) <= max(1e-9, 0.005 * abs(candidate)) or abs(x - candidate) < 1e-9:
                return True
    return False


def grounding(answer: str, tool_results: list[dict], question: str = "", context: dict | None = None) -> dict:
    """Every number in the answer must come from a tool result, the user's question, or the globe context."""
    source: set[float] = set()
    for r in tool_results or []:
        _walk_numbers(r, source)
    user = _numbers_in(question)
    _walk_numbers(context or {}, user)
    bad = sorted(n for n in _numbers_in(answer)
                 if n not in GROUND_CONSTANTS and not _allowed(n, source) and not _allowed(n, user))
    return {"score": float(not bad), "ungrounded_numbers": bad}


SAFE = re.compile(r"\b(safe|safer|safest|safely)\b", re.I)
NEGATED = re.compile(r"\b(not|isn't|aren't|never|no|n't|without)\b[^.]{0,25}$", re.I)
COLLISION = re.compile(r"collision probabilit", re.I)


def guardrails(answer: str, tool_results: list[dict]) -> dict:
    """README rules: never call a shell 'safe' (unless negated), never say 'collision probability' except quoting
    SOCRATES, say 'no tracked objects' for an empty region, and say 'tracked' when giving object counts."""
    problems = []
    text = answer or ""
    for m in SAFE.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        if not NEGATED.search(before):
            problems.append(f"says {m.group(0)!r} without a negation")
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if COLLISION.search(sentence) and "socrates" not in sentence.lower():
            problems.append("says 'collision probability' outside a SOCRATES quote")
    results = [r for r in (tool_results or []) if isinstance(r, dict) and r.get("ok")]
    empty = any((r.get("data") or {}).get("total") == 0 or (r.get("data") or {}).get("total_matches") == 0
                or (r.get("data") or {}).get("rows_available") == 0 for r in results)
    if empty and "no tracked objects" not in text.lower() and "no predicted" not in text.lower() and "no tracked" not in text.lower():
        problems.append("an empty result is not described as no tracked objects")
    if any(float(n) >= 2 for n in _numbers_in(text)) and results and not re.search(r"\b(tracked|catalog|socrates|predict)", text, re.I):
        problems.append("gives counts without saying they are tracked objects")
    return {"score": float(not problems), "problems": problems}


def json_valid(output) -> dict:
    """The agent returned the agreed shape: {answer: str, tool_calls: list of {name, args}}."""
    try:
        o = json.loads(output) if isinstance(output, str) else output
        ok = (isinstance(o, dict) and isinstance(o.get("answer"), str) and isinstance(o.get("tool_calls"), list)
              and all(isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("args", {}), dict) for c in o["tool_calls"]))
    except (ValueError, TypeError):
        ok = False
    return {"score": float(ok)}
