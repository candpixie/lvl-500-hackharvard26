"""Score a placement 0 to 100 (higher = safer) and rank shells. Backs POST /place and GET /rank.

Score = weighted mix of three things, each scaled 0 to 1 against the ranked shells (500 to 2,000 km)
(log scale, since they span orders of magnitude), so scores are relative to those shells (each factor is clamped, so 0 to 100 holds outside them):
  harm        collisions per year x years the wreckage stays up. A crash at 550 km clears in years,
              one at 1,500 km lingers for thousands. Lower is better. This is the main term.
  collisions  expected collisions per year (orbit_data.collision_rate), lower is better
  density     tracked objects per km^3 in the shell today, lower is better
Tracked objects only, so every risk number is a lower bound.
Close passes (SGP4 screen) are not in here yet; place() returns None for them.
Run from the repo root: uv run python pipeline/scoring.py
"""
import functools
import math

from orbit_data import SHELL_KM, collision_rate, dead_sat_lifetime_years, shells

# Tune these here. They should add up to 1.
WEIGHTS = {"harm": 0.8, "collisions": 0.1, "density": 0.1}
RANK_ALT_LO_KM, RANK_ALT_HI_KM = 500, 2000


@functools.cache
def shell_rows():
    return tuple(shells())


def factors(alt_km, dims_m, count):
    r = collision_rate(alt_km, dims_m, count, shell_rows())
    lifetime = dead_sat_lifetime_years(alt_km)
    return {
        "harm": r["collisions_per_year_total"] * lifetime,
        "collisions": r["collisions_per_year_total"],
        "density": r["shell"]["density_per_km3"],
        "lifetime": lifetime,
    }, r


def _log(x):
    return math.log10(max(x, 1e-12))


@functools.cache
def _ranges(dims_m, count):
    """Log min and max of each factor over the ranked shells, so scores compare across shells."""
    mids = [lo + SHELL_KM / 2 for lo in range(RANK_ALT_LO_KM, RANK_ALT_HI_KM, SHELL_KM)]
    all_f = [factors(m, dims_m, count)[0] for m in mids]
    return {k: (min(_log(f[k]) for f in all_f), max(_log(f[k]) for f in all_f)) for k in WEIGHTS}


def score(f, dims_m, count):
    """0 to 100, higher = safer. Also returns each factor's badness (0 best, 1 worst)."""
    badness = {}
    for k, (lo, hi) in _ranges(tuple(dims_m), count).items():
        badness[k] = 0.0 if hi == lo else min(max((_log(f[k]) - lo) / (hi - lo), 0.0), 1.0)
    return round(100 * (1 - sum(WEIGHTS[k] * b for k, b in badness.items())), 1), badness


def place(alt_km, inc_deg, dims_m, count=1):
    """Shell score, then shifted by how crowded this 10° inclination band is.

    The shell model (lifetime, density, first-order rate) is the same for every
    inclination. The shift uses tracked objects in the band versus the other
    bands in that shell: a fuller band scores lower, a quieter band scores higher.
    Tracked objects only, a lower bound. A band with nothing tracked is not empty space.
    """
    f, r = factors(alt_km, dims_m, count)
    shell_score, _ = score(f, dims_m, count)
    band = _band(alt_km, inc_deg)
    shifted = shell_score
    if band is not None:
        shifted = round(min(100.0, max(0.0, shell_score + (band["quiet"] - 0.5) * 24)), 1)
    out = {
        "alt_km": alt_km, "inc_deg": inc_deg, "dims_m": list(dims_m), "count": count,
        "shell": r["shell"],
        "objects_before": r["objects_before"],
        "objects_after": r["objects_after"],
        "collisions_per_year": r["collisions_per_year_total"],
        "collisions_per_year_one": r["collisions_per_year_one"],
        "close_passes": None,
        "nearest": None,
        "dead_sat_lifetime_years": f["lifetime"],
        "score": shifted,
        "shell_score": shell_score,
        "note": "tracked objects only, lower bound",
    }
    if band is not None:
        out["band_inc_lo"] = band["inc_lo"]
        out["band_inc_hi"] = band["inc_hi"]
        out["band_tracked"] = band["total"]
        out["band_debris"] = band["debris"]
    return out


def _band(alt_km, inc_deg):
    """Quietness of this inclination band inside its 50 km shell. 1 = fewest tracked objects."""
    from locations import _grid

    if not math.isfinite(alt_km) or not math.isfinite(inc_deg):
        return None
    alt_lo = int(math.floor(alt_km / 50.0) * 50)
    inc = min(max(float(inc_deg), 0.0), 180.0)
    inc_lo = 170 if inc >= 180 else int(math.floor(inc / 10.0) * 10)
    rows = [row for row in _grid() if row["alt_lo"] == alt_lo]
    if not rows:
        return None
    cell = next((row for row in rows if row["inc_lo"] == inc_lo), None)
    if cell is None:
        return None
    def quietness(values, value):
        lo, hi = min(values), max(values)
        if hi == lo:
            return 1.0
        return 1.0 - (value - lo) / (hi - lo)

    debris = [float(row.get("DEB") or 0) for row in rows]
    totals = [float(row["total"]) for row in rows]
    # Debris and satellites both crowd a band. Each is scaled against the other bands
    # in this shell, then averaged, so a band full of either one scores lower.
    quiet = 0.5 * quietness(debris, float(cell.get("DEB") or 0)) + 0.5 * quietness(totals, float(cell["total"]))
    return {
        "inc_lo": cell["inc_lo"],
        "inc_hi": cell["inc_hi"],
        "total": float(cell["total"]),
        "debris": float(cell.get("DEB") or 0),
        "quiet": quiet,
    }


def _years(y):
    return f"{y:.0f} years" if y >= 2 else "about a year"


def reason(f, shell):
    """One plain-English line for the ranking list."""
    return (f"{shell['total']:,.0f} tracked objects here today; "
            f"dead satellites fall out in about {_years(f['lifetime'])}.")


def rank(dims_m, count=1, top=10):
    """Shells from 500 to 2,000 km, safest first, each with a one-line reason. Backs GET /rank."""
    rows = []
    for lo in range(RANK_ALT_LO_KM, RANK_ALT_HI_KM, SHELL_KM):
        mid = lo + SHELL_KM / 2
        f, r = factors(mid, dims_m, count)
        s, _ = score(f, dims_m, count)
        rows.append({"alt_lo": lo, "alt_hi": lo + SHELL_KM, "score": s,
                     "collisions_per_year": f["collisions"], "dead_sat_lifetime_years": f["lifetime"],
                     "objects": r["shell"]["total"], "reason": reason(f, r["shell"])})
    return sorted(rows, key=lambda x: -x["score"])[:top]


def main():
    for count in (1, 1_000_000):
        print(f"\nTop shells for a 4x2x1 m satellite, count {count:,}:")
        for row in rank([4, 2, 1], count, top=5):
            print(f"  {row['alt_lo']:5d} km  score {row['score']:5.1f}  {row['reason']}")
    for alt in (550, 900):
        p = place(alt, 53, [4, 2, 1], 1_000_000)
        print(f"\nplace {alt} km, 1M sats: score {p['score']}, {p['collisions_per_year']:.0f} collisions/yr, "
              f"objects {p['objects_before']:,.0f} -> {p['objects_after']:,.0f}, "
              f"dead sats stay ~{p['dead_sat_lifetime_years']:.0f} yr")


if __name__ == "__main__":
    main()
