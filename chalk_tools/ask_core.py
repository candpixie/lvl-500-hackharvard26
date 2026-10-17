"""The Chalk reasoner behind POST $CHALK_ASK_URL (docs/chalk-contract.md). No Flask, no Chalk imports here.

Takes the user's question, decides which of the team's resolvers answers it, runs them, and returns
{answer, focus, tool_calls, note}. The resolvers are the team's own pipeline/orbit_data.py and
pipeline/scoring.py, unchanged, fed from the committed data/out/shells.json so the numbers match the globe and
the docs (safest shells 500 to 600 km for 4x2x1 m). Near misses come from the committed close_approaches.json,
with altitudes joined from the SATCAT catalog. No LLM: the rules below are deterministic so the eval is repeatable.

Paths come from the environment so the same code runs locally and in the Chalk container:
  ASK_PIPELINE (dir with orbit_data.py, scoring.py), ASK_DATA (dir with shells.json, close_approaches.json, catalog.csv.gz).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
import json
import math
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIMS_M = [4.0, 2.0, 1.0]
DEFAULT_INC_DEG = 53.0
NOTE = "tracked objects only, lower bound"
BAND_KM = 75.0  # how close to an altitude a near miss must be to count as "around" it (same as api/data.py)
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10}


def _paths():
    pipeline = Path(os.getenv("ASK_PIPELINE") or LOCAL_ROOT / "pipeline")
    data = Path(os.getenv("ASK_DATA") or LOCAL_ROOT / "data/out")
    return pipeline, data


class Resolvers:
    """The team's functions bound to the committed shell table. Built once per process."""

    def __init__(self):
        pipeline, data = _paths()
        self.shells_path = data / "shells.json"
        self.approaches_path = data / "close_approaches.json"
        self.catalog_path = next(c for c in (data / "catalog.csv.gz", data / "tools/catalog.csv.gz") if c.exists())
        if str(pipeline) not in sys.path:
            sys.path.insert(0, str(pipeline))
        import orbit_data
        rows = json.loads(self.shells_path.read_text())["shells"]
        orbit_data.shells = lambda cat=None: rows  # use the committed table; scoring imports this name after the patch
        import scoring
        self.orbit_data, self.scoring, self.shell_rows = orbit_data, scoring, rows
        self.snapshot = {k: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for k, p in
                         (("shells", self.shells_path), ("close_approaches", self.approaches_path))}

    def shell(self, alt_km: float) -> dict:
        for row in self.shell_rows:
            if row["alt_lo"] <= alt_km < row["alt_hi"]:
                return {"note": NOTE, **row}
        raise ValueError(f"altitude {alt_km} km is outside the 300 to 2,000 km shells")

    @lru_cache(maxsize=1)
    def approaches(self) -> list[dict]:
        import pandas as pd
        cat = pd.read_csv(self.catalog_path).set_index("NORAD_CAT_ID").mean_alt
        rows = []
        for r in json.loads(self.approaches_path.read_text())["rows"]:
            alts = [cat.get(int(r[k])) for k in ("norad_1", "norad_2")]
            known = [float(a) for a in alts if a is not None and not math.isnan(a)]
            when = datetime.strptime(str(r["time_utc"])[:10], "%Y-%m-%d")
            rows.append({**r, "mean_alt_km": sum(known) / len(known) if known else None,
                         "date_text": f"{when:%B} {when.day}"})
        return rows

    def near_misses(self, alt_km: float | None, limit: int = 3) -> list[dict]:
        rows = self.approaches()
        if alt_km is not None:
            rows = [r for r in rows if r["mean_alt_km"] is not None and abs(r["mean_alt_km"] - alt_km) <= BAND_KM]
        return sorted(rows, key=lambda r: r["miss_distance_km"])[:limit]


@lru_cache(maxsize=1)
def resolvers() -> Resolvers:
    return Resolvers()


# ---------- reading the question ----------

def _number(text: str) -> float:
    return float(text.replace(",", ""))


def parse_question(q: str) -> dict:
    t = q.lower().replace("’", "'")
    out = {"intent": None, "alt_km": None, "count": None, "dims_m": None, "inc_deg": None}
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(?:km|kilometers?|kilometres?)\b", t)
    if m:
        out["alt_km"] = _number(m.group(1))
    m = re.search(r"\b(\d+(?:\.\d+)?|one|two|three|four|five|six|eight|ten)[\s-]*(?:m|meters?|metres?)\b", t)
    if m:
        length = WORD_NUM.get(m.group(1)) or float(m.group(1))
        out["dims_m"] = [float(length), length / 2, length / 4]
    m = re.search(r"\b(?:(a|one)\s+million|(\d[\d,]*\.?\d*)\s*(million|thousand|m|k)?)\s*(?:[\w-]+\s+){0,3}?(?:satellites?|sats?|spacecraft|cubesats?)\b", t)
    if m:
        if m.group(1):
            out["count"] = 1_000_000
        else:
            n = _number(m.group(2))
            n *= {"million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}.get(m.group(3), 1)
            out["count"] = int(n)
    elif re.search(r"\b(a|my|one|the)\s+(?:[\w-]+\s+){0,2}(?:satellite|sat|spacecraft|cubesat)\b", t):
        out["count"] = 1
    for pattern, inc in ((r"sun[- ]?synchronous|\bsso\b", 98.0), (r"\bpolar\b", 90.0), (r"\biss\b|space station", 51.6), (r"equatorial", 0.0)):
        if re.search(pattern, t):
            out["inc_deg"] = inc
            break
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:degrees?|°|deg)\b", t)
    if m and out["inc_deg"] is None and 0 <= float(m.group(1)) <= 180:
        out["inc_deg"] = float(m.group(1))
    if re.search(r"near[- ]?miss|close approach|closest|close call", t):
        out["intent"] = "near_miss"
    elif re.search(r"\bwhy\b", t) and out["alt_km"] is not None:
        out["intent"] = "why"
    elif re.search(r"what (?:happens )?if|what would happen|suppose", t) and out["alt_km"] is not None:
        out["intent"] = "place"
    elif re.search(r"\bwhere\b|best (?:orbit|altitude|shell)|recommend|which (?:orbit|altitude|shell)", t):
        out["intent"] = "rank"
    elif out["alt_km"] is not None:
        out["intent"] = "place" if out["count"] else "crowding"
    return out


# ---------- answering ----------

def _r(x, digits=0):
    return round(x, digits) if digits else int(round(x))


def _years(y: float) -> str:
    return "about a year" if y < 2 else f"roughly {_r(y):,} years"


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 1) if abs(value) >= 100 else float(f"{value:.3g}")
    return value


def _call(name: str, arguments: dict, result) -> dict:
    return {"name": name, "arguments": arguments, "result": _clean(result)}


def _pair(r: dict) -> str:
    return f"{r['name_1'].split(' [')[0]} and {r['name_2'].split(' [')[0]}"


NOTE_SENTENCE = "Everything here counts tracked objects only, so it is a lower bound."


def _rate(x: float) -> str:
    if x >= 100:
        return f"{x:,.0f}"
    if x >= 1:
        return f"{x:.1f}"
    return f"{x:.3g}"


def _near_miss_sentence(r: dict) -> str:
    meters = r["miss_distance_km"] * 1000
    return (f"SOCRATES predicts {_pair(r)} will pass {meters:,.0f} meters apart at "
            f"{r['relative_speed_km_s']:.1f} kilometers per second on {r['date_text']}; that is a SOCRATES prediction, "
            f"not a probability we computed.")


def answer(question: str) -> dict:
    """Returns the /ask body, or {"error": reason} when the question is outside what these resolvers answer."""
    R = resolvers()
    p = parse_question(question or "")
    dims = p["dims_m"] or DEFAULT_DIMS_M
    inc = p["inc_deg"] if p["inc_deg"] is not None else DEFAULT_INC_DEG
    count = p["count"] or 1
    length = max(dims)
    sc = R.scoring
    if p["intent"] == "near_miss":
        rows = R.near_misses(p["alt_km"], 3)
        if not rows:
            where = f" around {_r(p['alt_km'])} km" if p["alt_km"] is not None else ""
            return {"answer": f"SOCRATES lists no predicted close approaches{where} in the closest 500 this week. {NOTE.capitalize()}.",
                    "focus": None, "tool_calls": [_call("get_close_approaches", {"alt_km": p["alt_km"]}, [])], "note": NOTE}
        top = rows[0]
        focus_alt = _r(top["mean_alt_km"]) if top["mean_alt_km"] is not None else None
        text = (_near_miss_sentence(top) + (f" The two objects are at about {_r(top['mean_alt_km'])} kilometers."
                                              if top["mean_alt_km"] is not None else "") + f" {NOTE_SENTENCE}")
        return {"answer": text, "focus": {"altitude_km": focus_alt, "inclination_deg": inc} if focus_alt else None,
                "tool_calls": [_call("get_close_approaches", {"alt_km": p["alt_km"], "limit": 3}, rows)], "note": NOTE}
    if p["intent"] == "why":
        row = R.shell(p["alt_km"])
        best = sc.rank(dims, count, top=1)[0]
        near = R.near_misses(row["alt_lo"] + 25, 1)
        debris_note = "mostly debris" if row["DEB"] >= 0.5 * row["total"] else "a mix of satellites and debris"
        life = R.orbit_data.dead_sat_lifetime_years(row["alt_lo"] + 25)
        row = {**row, "dead_sat_lifetime_years": life}
        text = (f"The {row['alt_lo']} to {row['alt_hi']} kilometer shell holds about {_r(row['total']):,} tracked objects, {debris_note}: "
                f"{_r(row['DEB']):,} debris pieces against {_r(row['PAY']):,} satellites. "
                f"A dead satellite there would stay up {_years(life)} because there is little drag to bring it down, "
                f"against {_years(best['dead_sat_lifetime_years'])} in the {best['alt_lo']} to {best['alt_hi']} kilometer shell (a rough estimate). "
                + (_near_miss_sentence(near[0]) + " " if near else "") + NOTE_SENTENCE)
        return {"answer": text, "focus": {"altitude_km": row["alt_lo"] + 25, "inclination_deg": inc},
                "tool_calls": [_call("get_shell_crowding", {"alt_km": p["alt_km"]}, row),
                               _call("get_close_approaches", {"alt_km": row["alt_lo"] + 25, "limit": 1}, near),
                               _call("rank_shells", {"count": count, "dims_m": dims, "top": 1}, [best])], "note": NOTE}
    if p["intent"] == "crowding":
        row = R.shell(p["alt_km"])
        life = R.orbit_data.dead_sat_lifetime_years(row["alt_lo"] + 25)
        row = {**row, "dead_sat_lifetime_years": life}
        text = (f"The {row['alt_lo']} to {row['alt_hi']} kilometer shell holds about {_r(row['total']):,} tracked objects: "
                f"{_r(row['PAY']):,} satellites, {_r(row['DEB']):,} debris pieces and {_r(row['R/B']):,} rocket bodies. "
                f"A dead satellite there would stay up {_years(life)} (a rough estimate). {NOTE_SENTENCE}")
        return {"answer": text, "focus": {"altitude_km": p["alt_km"], "inclination_deg": inc},
                "tool_calls": [_call("get_shell_crowding", {"alt_km": p["alt_km"]}, row)], "note": NOTE}
    if p["intent"] == "place":
        alt = p["alt_km"]
        res = sc.place(alt, inc, dims, count)
        best = sc.rank(dims, count, top=1)[0]
        shell = res["shell"]
        who = f"{count:,} satellites about {_r(length)} meters long" if count > 1 else f"one satellite about {_r(length)} meters long"
        text = (f"At {_r(alt)} kilometers, {who} would take the {shell['alt_lo']} to {shell['alt_hi']} kilometer shell from "
                f"about {_r(res['objects_before']):,} to {_r(res['objects_after']):,} tracked objects. "
                f"The first-order model gives about {_rate(res['collisions_per_year'])} expected collisions per year with tracked objects, "
                f"and a dead satellite there would stay up {_years(res['dead_sat_lifetime_years'])}. "
                f"That scores {_r(res['score'])} out of 100, against {_r(best['score'])} for {best['alt_lo']} to {best['alt_hi']} kilometers. "
                f"{NOTE_SENTENCE}")
        return {"answer": text, "focus": {"altitude_km": alt, "inclination_deg": inc},
                "tool_calls": [_call("place_satellites", {"alt_km": alt, "inc_deg": inc, "dims_m": dims, "count": count}, res),
                               _call("rank_shells", {"count": count, "dims_m": dims, "top": 1}, [best])], "note": NOTE}
    if p["intent"] == "rank":
        rows = sc.rank(dims, count, top=3)
        top = rows[0]
        who = f"{count:,} satellites about {_r(length)} meters long" if count > 1 else f"a satellite about {_r(length)} meters long"
        text = (f"For {who}, the lowest-harm shells I can see are {top['alt_lo']} to {top['alt_hi']} kilometers, then "
                f"{rows[1]['alt_lo']} to {rows[1]['alt_hi']} and {rows[2]['alt_lo']} to {rows[2]['alt_hi']}. "
                f"The top shell holds about {_r(top['objects']):,} tracked objects today, and a dead satellite there would come down in "
                f"{_years(top['dead_sat_lifetime_years'])}. {NOTE_SENTENCE}")
        return {"answer": text, "focus": {"altitude_km": top["alt_lo"] + 25, "inclination_deg": inc},
                "tool_calls": [_call("rank_shells", {"count": count, "dims_m": dims, "top": 3}, rows)], "note": NOTE}
    return {"error": "I can answer where to place satellites, what happens at an altitude, why an altitude is crowded, "
                     "and the closest near miss this week."}
