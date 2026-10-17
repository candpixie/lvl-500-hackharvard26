"""Chalk evaluation task and scorer for the headline eval (recommend_orbit vs baselines).

WARNING: importing this module deploys the two functions to Chalk. Run the eval with
    uv run --with chalkcompute --with chalkpy python -m chalk_tools.run_eval

The task never receives the answer key; the scorer gets it from the dataset row only.
"""
from __future__ import annotations

import json
import math
import random

import chalkcompute

from chalk_tools import core
from chalk_tools.shared import IMAGE, snapshot


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def pick_orbit(picker: str, seed: int, inclination_deg: float, min_altitude_km: float, max_altitude_km: float,
               inclination_band_deg: float) -> str:
    """Pick one 50 km shell for a mission. picker: recommend | count_in_plane | web_rule | random."""
    snap = snapshot()
    shells = list(range(int(min_altitude_km // core.SHELL_KM * core.SHELL_KM), int(math.ceil(max_altitude_km / core.SHELL_KM) * core.SHELL_KM), core.SHELL_KM))
    with chalkcompute.span(f"eval.pick.{picker}"):
        if picker == "recommend":
            res = core.recommend_orbit(snap, inclination_deg, min_altitude_km, max_altitude_km, top_n=1,
                                       inclination_band_deg=inclination_band_deg)
            shell = res["data"]["candidates"][0]["shell_km"][0]
        elif picker == "count_in_plane":  # fewest objects by average altitude near this inclination
            shell = min(shells, key=lambda s: (core.shell_crowding(snap, s, inclination_deg, inclination_band_deg)["data"]["total"], s))
        elif picker == "web_rule":  # the web app's current rule: fewest objects by average altitude, any inclination
            shell = min(shells, key=lambda s: (core.shell_crowding(snap, s)["data"]["total"], s))
        elif picker == "random":
            shell = random.Random(seed * 1_000_003 + int(inclination_deg * 10)).choice(shells)
        else:
            raise ValueError(f"unknown picker {picker!r}")
    return json.dumps({"picker": picker, "shell_km": int(shell)})


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def shell_safety(output: str, events_by_shell: str) -> float:
    """1.0 if the picked shell has the fewest SOCRATES near misses of all shells in the band, 0.0 the most, ties half."""
    shell = int(json.loads(output)["shell_km"])
    events = {int(k): int(v) for k, v in json.loads(events_by_shell).items()}
    if shell not in events or len(events) < 2:
        raise ValueError(f"shell {shell} not in answer key")
    mine = events[shell]
    worse = sum(v > mine for v in events.values())
    ties = sum(v == mine for v in events.values()) - 1
    return (worse + 0.5 * ties) / (len(events) - 1)
