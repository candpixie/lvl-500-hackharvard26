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
import os
from functools import lru_cache
from pathlib import Path

import chalkcompute
from chalkcompute import Image

from chalk_tools import core

LOCAL_TOOLS_DIR = core.ROOT / "data/out/tools"
REMOTE_TOOLS_DIR = "/app/tools_data"

IMAGE = (
    Image.debian_slim("3.12")
    .pip_install(["pandas", "numpy"])
    .add_local_dir(str(LOCAL_TOOLS_DIR), REMOTE_TOOLS_DIR, strategy="volume")  # "copy" caps files at 32 KiB
)


@lru_cache(maxsize=1)
def _snapshot() -> core.Snapshot:
    """Loaded once per container; the remote image has the data at REMOTE_TOOLS_DIR."""
    remote = Path(REMOTE_TOOLS_DIR)
    return core.Snapshot.load_compact(remote if remote.exists() else LOCAL_TOOLS_DIR)


def _run(name: str, fn, **kwargs) -> str:
    with chalkcompute.span(f"tool.{name}"):
        return json.dumps(fn(_snapshot(), **kwargs))


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def shell_crowding(altitude_km: float, inclination_deg: float | None = None) -> str:
    return _run("shell_crowding", core.shell_crowding, altitude_km=altitude_km, inclination_deg=inclination_deg)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def objects_near(altitude_km: float, inclination_deg: float, limit: int = 10) -> str:
    return _run("objects_near", core.objects_near, altitude_km=altitude_km,
                inclination_deg=inclination_deg, limit=limit)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def close_approaches(min_altitude_km: float, max_altitude_km: float, limit: int = 10) -> str:
    return _run("close_approaches", core.close_approaches, min_altitude_km=min_altitude_km,
                max_altitude_km=max_altitude_km, limit=limit)


@chalkcompute.function(image=IMAGE, tracing=True, cpu="1", memory="2Gi")
def recommend_orbit(inclination_deg: float, min_altitude_km: float = 400.0, max_altitude_km: float = 1200.0,
                    top_n: int = 5, inclination_band_deg: float = 10.0) -> str:
    return _run("recommend_orbit", core.recommend_orbit, inclination_deg=inclination_deg,
                min_altitude_km=min_altitude_km, max_altitude_km=max_altitude_km, top_n=top_n,
                inclination_band_deg=inclination_band_deg)


if __name__ == "__main__":
    # Smoke test of the deployed functions; one cheap call each.
    print(json.loads(shell_crowding.remote(550.0))["data"]["counts"])
    print(json.loads(objects_near.remote(420.0, 51.6, 3))["data"]["total_matches"])
    print(json.loads(close_approaches.remote(400.0, 600.0, 1))["data"]["approaches"][0]["miss_distance_m"])
    print([c["shell_km"][0] for c in json.loads(recommend_orbit.remote(53.0))["data"]["candidates"]])
