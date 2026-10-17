"""Chalk functions for the orbit agent: thin wrappers over chalk_tools.core.

WARNING: importing this module deploys the functions to Chalk (the decorator registers them as soon as the
module runs). Tests and local code must import chalk_tools.core, never this file. Deploy on purpose with:
    uv run python -m chalk_tools.functions

Each function returns the JSON text of the standard envelope (see core.py) because Chalk derives its
wire schema from type hints and a JSON string is the safest type for a nested result. Callers json.loads it.
The data (data/out/tools, built by pipeline/build_tools_data.py) is copied into the image at deploy time.
"""
from __future__ import annotations

import json
import time

import chalkcompute

from chalk_tools import core
from chalk_tools.shared import IMAGE, snapshot as _snapshot


SLOW_MS = 3000
REV = "3"  # bump to force a new function version when only helper code changed


def _run(name: str, fn, **kwargs) -> str:
    """Run one tool and write one log line per call, so the Chalk dashboard can count calls (Chalk's own queue
    metrics do not count direct .remote() calls)."""
    started = time.perf_counter()
    with chalkcompute.span(f"tool.{name}"):
        result = fn(_snapshot(), **kwargs)
    ms = (time.perf_counter() - started) * 1000
    print(f"tool_call tool={name} ok={bool(result.get('ok'))} ms={ms:.1f} snapshot={result.get('snapshot_id')} "
          f"args={json.dumps(kwargs, sort_keys=True, default=str)}", flush=True)
    if ms >= SLOW_MS:  # a separate marker so a log monitor can alert on slow calls (log monitors cannot compare numbers)
        print(f"tool_slow tool={name} ms={ms:.1f} limit_ms={SLOW_MS}", flush=True)
    return json.dumps(result)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def shell_crowding(altitude_km: float, inclination_deg: float | None = None) -> str:
    _ = REV
    return _run("shell_crowding", core.shell_crowding, altitude_km=altitude_km, inclination_deg=inclination_deg)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def objects_near(altitude_km: float, inclination_deg: float, limit: int = 10) -> str:
    _ = REV
    return _run("objects_near", core.objects_near, altitude_km=altitude_km,
                inclination_deg=inclination_deg, limit=limit)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def close_approaches(min_altitude_km: float, max_altitude_km: float, limit: int = 10) -> str:
    _ = REV
    return _run("close_approaches", core.close_approaches, min_altitude_km=min_altitude_km,
                max_altitude_km=max_altitude_km, limit=limit)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def recommend_orbit(inclination_deg: float, min_altitude_km: float = 400.0, max_altitude_km: float = 1200.0,
                    top_n: int = 5, inclination_band_deg: float = 10.0) -> str:
    _ = REV
    return _run("recommend_orbit", core.recommend_orbit, inclination_deg=inclination_deg,
                min_altitude_km=min_altitude_km, max_altitude_km=max_altitude_km, top_n=top_n,
                inclination_band_deg=inclination_band_deg)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def launch_kind_profile(kind: str) -> str:
    _ = REV
    return _run("launch_kind_profile", core.launch_kind_profile, kind=kind)


if __name__ == "__main__":
    # Smoke test of the deployed functions; one cheap call each.
    print(json.loads(shell_crowding.remote(550.0))["data"]["counts"])
    print(json.loads(objects_near.remote(420.0, 51.6, 3))["data"]["total_matches"])
    print(json.loads(close_approaches.remote(400.0, 600.0, 1))["data"]["approaches"][0]["miss_distance_m"])
    print([c["shell_km"][0] for c in json.loads(recommend_orbit.remote(53.0))["data"]["candidates"]])
