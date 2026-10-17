"""Cache SATCAT-backed scores and SOCRATES lookups. Tools the agent calls live here."""
from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from orbit_data import SHELL_KM, shells  # noqa: E402
from scoring import place, rank  # noqa: E402

OUT = ROOT / "data/out"
DEFAULT_DIMS_M = [4.0, 2.0, 1.0]
DEFAULT_INC_DEG = 53.0
SHELL_HALF_KM = SHELL_KM / 2


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if abs(value) >= 100:
            return round(value, 1)
        if abs(value) >= 1:
            return round(value, 2)
        return float(f"{value:.3g}")
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value


@lru_cache(maxsize=1)
def shell_rows() -> list[dict]:
    built = OUT / "shells.json"
    try:
        return json_safe(list(shells()))
    except FileNotFoundError:
        if built.exists():
            return json.loads(built.read_text())["shells"]
        raise


def get_shell_crowding(alt_km: float) -> dict:
    rows = shell_rows()
    for row in rows:
        if row["alt_lo"] <= alt_km < row["alt_hi"] or (
            alt_km == row["alt_hi"] and row["alt_hi"] == rows[-1]["alt_hi"]
        ):
            return {"note": "tracked objects only, lower bound", **row}
    raise ValueError(f"altitude {alt_km} km is outside the 300 to 2,000 km shells")


def place_satellites(alt_km: float, inc_deg: float, dims_m: list[float], count: int) -> dict:
    return json_safe(place(alt_km, inc_deg, dims_m, count))


def rank_shells(dims_m: list[float], count: int, top: int = 10) -> list[dict]:
    return json_safe(rank(dims_m, count, top=top))


@lru_cache(maxsize=1)
def _object_alts() -> dict[int, dict]:
    path = OUT / "objects.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    out = {}
    for obj in payload.get("objects", []):
        apogee, perigee = obj.get("apogee_km"), obj.get("perigee_km")
        alt = None
        if apogee is not None and perigee is not None:
            alt = (float(apogee) + float(perigee)) / 2
        out[int(obj["norad"])] = {
            "name": obj.get("name"),
            "type": obj.get("type"),
            "alt_km": alt,
            "inclination_deg": obj.get("omm", {}).get("INCLINATION"),
        }
    return out


@lru_cache(maxsize=1)
def close_approach_rows() -> list[dict]:
    path = OUT / "close_approaches.json"
    if not path.exists():
        return []
    alts = _object_alts()
    rows = []
    for row in json.loads(path.read_text()).get("rows", []):
        a1 = alts.get(int(row["norad_1"]), {})
        a2 = alts.get(int(row["norad_2"]), {})
        known = [a["alt_km"] for a in (a1, a2) if a.get("alt_km") is not None]
        rows.append({
            **row,
            "alt_km_1": a1.get("alt_km"),
            "alt_km_2": a2.get("alt_km"),
            "mean_alt_km": sum(known) / len(known) if known else None,
            "type_1": a1.get("type"),
            "type_2": a2.get("type"),
        })
    return rows


def get_close_approaches(alt_km: float | None = None, limit: int = 10, band_km: float = 75.0) -> dict:
    rows = close_approach_rows()
    if alt_km is not None:
        rows = [
            r for r in rows
            if any(
                r.get(k) is not None and abs(r[k] - alt_km) <= band_km
                for k in ("alt_km_1", "alt_km_2", "mean_alt_km")
            )
        ]
    rows = sorted(rows, key=lambda r: r["miss_distance_km"])[: max(1, min(int(limit), 50))]
    return {
        "source": "CelesTrak SOCRATES, same-constellation pairs removed; tracked objects only",
        "alt_km": alt_km,
        "count": len(rows),
        "rows": json_safe(rows),
    }


def focus_from_place(result: dict) -> dict:
    out = {
        "altitude_km": result["alt_km"],
        "inclination_deg": result.get("inc_deg", DEFAULT_INC_DEG),
    }
    if result.get("count") is not None:
        out["count"] = result["count"]
    if result.get("dims_m") is not None:
        out["dims_m"] = result["dims_m"]
    return out


def focus_from_rank(rows: list[dict], inc_deg: float = DEFAULT_INC_DEG) -> dict | None:
    if not rows:
        return None
    top = rows[0]
    return {
        "altitude_km": top["alt_lo"] + SHELL_HALF_KM,
        "inclination_deg": inc_deg,
    }


def warmup() -> None:
    shell_rows()
    close_approach_rows()
