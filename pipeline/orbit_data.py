"""Crowding by orbit shell, a first-order collision rate, and how long dead satellites stay up.

Source: CelesTrak SATCAT (data/raw/celestrak/satcat.csv from fetch_orbits.py). Tracked objects only,
so every number here is a lower bound: untracked debris (under about 10 cm) is not counted.
Each object's time is spread evenly between its perigee and apogee (simple, and said so on screen).
Outputs:
  data/out/shells.json         one row per 50 km shell: counts by type, density (objects/km^3)
  data/out/crowding_grid.json  altitude x inclination grid by type, for the heatmap
  data/out/decay_table.json    approximate dead-satellite lifetime by altitude
Run from the repo root: uv run python pipeline/orbit_data.py
"""
import json
import math
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SATCAT = ROOT / "data/raw/celestrak/satcat.csv"
OUT = ROOT / "data/out"

EARTH_RADIUS_KM = 6371.0
SECONDS_PER_YEAR = 3.156e7
ALT_LO_KM, ALT_HI_KM, SHELL_KM = 300, 2000, 50
INC_STEP_DEG = 10
TYPES = ["PAY", "R/B", "DEB", "UNK"]
V_REL_KMS = 10.0     # typical relative speed between two objects in low Earth orbit
R_DEBRIS_M = 0.5     # typical radius of the tracked object we might hit

# Approximate years a dead satellite stays up before drag brings it down, for moderate solar activity
# and a typical satellite. Rough anchors from the usual rule-of-thumb tables; the real answer
# depends on solar activity and the satellite's area-to-mass ratio by about 10x either way.
# Verify against a published source before putting it on a slide.
DECAY_ANCHORS = [  # (altitude_km, years)
    (300, 0.1), (400, 1), (500, 8), (600, 25), (700, 100), (800, 200),
    (900, 500), (1000, 1000), (1200, 3000), (1500, 8000), (2000, 20000),
]

ALT_EDGES_KM = np.arange(ALT_LO_KM, ALT_HI_KM + SHELL_KM, SHELL_KM)
INC_EDGES_DEG = np.arange(0, 180 + INC_STEP_DEG, INC_STEP_DEG)


def load_catalog():
    """Tracked objects still orbiting Earth, with any part of their orbit in our altitude range."""
    d = pd.read_csv(SATCAT)
    d = d[d.DECAY_DATE.isna() & (d.ORBIT_CENTER == "EA")]
    d = d.dropna(subset=["APOGEE", "PERIGEE", "INCLINATION"])
    d = d[(d.PERIGEE < ALT_HI_KM) & (d.APOGEE > ALT_LO_KM)]
    d = d.assign(OBJECT_TYPE=d.OBJECT_TYPE.where(d.OBJECT_TYPE.isin(TYPES), "UNK"))
    return d.reset_index(drop=True)


def residence(perigee_km, apogee_km):
    """Fraction of each object's time in each shell, shape (objects, shells).

    Time is spread evenly between perigee and apogee. Time above or below our range is dropped.
    """
    p = np.asarray(perigee_km, float)[:, None]
    a = np.maximum(np.asarray(apogee_km, float), p[:, 0] + 1e-6)[:, None]
    lo, hi = ALT_EDGES_KM[None, :-1], ALT_EDGES_KM[None, 1:]
    overlap = np.clip(np.minimum(a, hi) - np.maximum(p, lo), 0, None)
    return overlap / (a - p)


def shell_volume_km3(alt_lo_km, alt_hi_km):
    return 4 / 3 * math.pi * ((EARTH_RADIUS_KM + alt_hi_km) ** 3 - (EARTH_RADIUS_KM + alt_lo_km) ** 3)


def shell_index(alt_km):
    i = int((alt_km - ALT_LO_KM) // SHELL_KM)
    if not 0 <= i < len(ALT_EDGES_KM) - 1:
        raise ValueError(f"altitude {alt_km} km is outside {ALT_LO_KM} to {ALT_HI_KM} km")
    return i


def shells(cat=None):
    """One row per shell: objects by type (time-weighted, so fractional), total, density per km^3."""
    cat = load_catalog() if cat is None else cat
    res = residence(cat.PERIGEE, cat.APOGEE)
    rows = []
    for i, (lo, hi) in enumerate(zip(ALT_EDGES_KM[:-1], ALT_EDGES_KM[1:])):
        counts = {t: float(res[(cat.OBJECT_TYPE == t).to_numpy(), i].sum()) for t in TYPES}
        total = sum(counts.values())
        rows.append({
            "alt_lo": int(lo), "alt_hi": int(hi),
            **{t: round(c, 1) for t, c in counts.items()},
            "total": round(total, 1),
            "density_per_km3": total / shell_volume_km3(lo, hi),
        })
    return rows


def crowding_grid(cat=None):
    """Altitude x inclination counts by type, for the heatmap. Dense rows, one per (shell, inclination band)."""
    cat = load_catalog() if cat is None else cat
    res = residence(cat.PERIGEE, cat.APOGEE)
    inc_bin = np.clip(np.digitize(cat.INCLINATION, INC_EDGES_DEG) - 1, 0, len(INC_EDGES_DEG) - 2)
    rows = []
    for i, lo in enumerate(ALT_EDGES_KM[:-1]):
        for j, inc_lo in enumerate(INC_EDGES_DEG[:-1]):
            in_bin = inc_bin == j
            counts = {t: round(float(res[in_bin & (cat.OBJECT_TYPE == t).to_numpy(), i].sum()), 1) for t in TYPES}
            rows.append({"alt_lo": int(lo), "alt_hi": int(lo + SHELL_KM),
                         "inc_lo": int(inc_lo), "inc_hi": int(inc_lo + INC_STEP_DEG),
                         **counts, "total": round(sum(counts.values()), 1)})
    return rows


def collision_rate(alt_km, dims_m, count=1, shell_rows=None, v_rel_kms=V_REL_KMS, r_debris_m=R_DEBRIS_M):
    """Expected collisions per year with tracked objects, first-order kinetic-gas model.

    rate per object = n * v_rel * A, with n = shell density, A = pi * (r_obj + r_debris)^2 and
    r_obj = half the longest dimension. For a constellation of `count`, each object also sees the
    other count-1 added to its shell (self-crowding). Tracked objects only: a lower bound.
    """
    shell_rows = shells() if shell_rows is None else shell_rows
    s = shell_rows[shell_index(alt_km)]
    volume = shell_volume_km3(s["alt_lo"], s["alt_hi"])
    area_km2 = math.pi * ((max(dims_m) / 2 + r_debris_m) / 1000) ** 2
    per_object = s["density_per_km3"] * v_rel_kms * area_km2 * SECONDS_PER_YEAR
    density_after = (s["total"] + count - 1) / volume
    per_object_after = density_after * v_rel_kms * area_km2 * SECONDS_PER_YEAR
    return {
        "shell": s,
        "objects_before": s["total"],
        "objects_after": s["total"] + count,
        "collisions_per_year_one": per_object,
        "collisions_per_year_total": per_object_after * count,
        "note": "tracked objects only, lower bound",
    }


def dead_sat_lifetime_years(alt_km):
    """Approximate years a dead satellite at this altitude stays up (log-interpolated)."""
    alts, years = zip(*DECAY_ANCHORS)
    return float(10 ** np.interp(alt_km, alts, np.log10(years)))


def main():
    cat = load_catalog()
    shell_rows = shells(cat)
    grid = crowding_grid(cat)
    source = "CelesTrak SATCAT, tracked objects only (lower bound), time spread evenly between perigee and apogee"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shells.json").write_text(json.dumps({"source": source, "shells": shell_rows}, indent=1))
    (OUT / "crowding_grid.json").write_text(json.dumps({
        "source": source, "alt_step_km": SHELL_KM, "inc_step_deg": INC_STEP_DEG, "types": TYPES, "rows": grid,
    }))
    decay = [{"alt_km": int(a), "years": round(dead_sat_lifetime_years(a), 2)} for a in ALT_EDGES_KM]
    (OUT / "decay_table.json").write_text(json.dumps({
        "source": "approximate rule-of-thumb anchors, moderate solar activity; depends on solar activity "
                  "and satellite shape by about 10x, verify before a slide",
        "rows": decay,
    }, indent=1))

    print(f"{len(cat)} tracked objects with orbits in {ALT_LO_KM} to {ALT_HI_KM} km")
    peak = max(shell_rows, key=lambda r: r["DEB"])
    ok = 700 <= peak["alt_lo"] <= 850
    print(f"debris peak: {peak['alt_lo']} to {peak['alt_hi']} km, {peak['DEB']:.0f} pieces "
          f"({'OK' if ok else 'CHECK PIPELINE'}, expect about 750 to 850 km)")
    for alt in (550, 900):
        r = collision_rate(alt, [4, 2, 1], 1, shell_rows)
        big = collision_rate(alt, [4, 2, 1], 1_000_000, shell_rows)
        print(f"{alt} km, 4x2x1 m: one sat {r['collisions_per_year_one']:.2e}/yr; "
              f"1M sats {big['collisions_per_year_total']:.0f}/yr; dead sat stays ~{dead_sat_lifetime_years(alt):.0f} yr")


if __name__ == "__main__":
    main()
