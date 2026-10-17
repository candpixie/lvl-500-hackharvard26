"""SOCRATES answer key for evaluating recommend_orbit. Never imported by the Chalk tool functions.

A near-miss rate per (shell, inclination band) from every filtered SOCRATES row (all 196,744 minus the same
filters the tools use). Rate = predicted close approaches per 1,000 tracked objects in that shell and inclination
band. Caveats: SOCRATES only reports pairs with at least one active satellite, covers one week, and our shells
use average altitude; so this is a test of whether the crowding index tracks predicted near misses, not a
measure of collision risk.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from chalk_tools import core

MIN_OBJECTS = 20  # shells with fewer objects give unstable rates; leave them out of an evaluation


def events(snap: core.Snapshot) -> pd.DataFrame:
    inc = snap.catalog.set_index("NORAD_CAT_ID").INCLINATION
    a = snap.approaches
    e = a.assign(inc_1=a.NORAD_CAT_ID_1.map(inc), inc_2=a.NORAD_CAT_ID_2.map(inc))
    return e.dropna(subset=["pair_alt", "inc_1", "inc_2"])


def shell_rates(snap: core.Snapshot, ev: pd.DataFrame, inclination_deg: float, min_alt: float, max_alt: float,
                band_deg: float = 10.0, max_range_km: float | None = None) -> pd.DataFrame:
    """One row per 50 km shell in [min_alt, max_alt): objects, events, and three candidate measures.

    events: raw predicted close approaches in the shell (exposure: where near misses actually happen).
    rate_per_1000: events per 1,000 tracked objects. rate_indep: events per 1,000 objects that are not members
    of a big constellation (our SOCRATES filter removes constellation-vs-itself pairs, which deflates the
    per-object rate in constellation shells).
    """
    e = ev if max_range_km is None else ev[ev.TCA_RANGE <= max_range_km]
    # An event counts if at least one of its two objects is in the inclination band, matching the object count
    # below (averaging the two inclinations would put a 30-degree object meeting a 76-degree one in a 53 band).
    e = e[((e.inc_1 - inclination_deg).abs() <= band_deg) | ((e.inc_2 - inclination_deg).abs() <= band_deg)]
    rows = []
    for lo in range(int(min_alt // core.SHELL_KM * core.SHELL_KM), int(max_alt), core.SHELL_KM):
        n_obj = core.shell_crowding(snap, lo, inclination_deg, band_deg)["data"]["total"]
        c = snap.catalog
        inshell = c[(c.mean_alt >= lo) & (c.mean_alt < lo + core.SHELL_KM) & ((c.INCLINATION - inclination_deg).abs() <= band_deg)]
        n_ind = int(inshell.OBJECT_NAME.map(core.constellation).isna().sum())
        n_ev = int(((e.pair_alt >= lo) & (e.pair_alt < lo + core.SHELL_KM)).sum())
        rows.append({"shell_km": lo, "objects": n_obj, "events": n_ev,
                     "rate_per_1000": n_ev / n_obj * 1000 if n_obj >= MIN_OBJECTS else np.nan,
                     "rate_indep": n_ev / n_ind * 1000 if n_ind >= MIN_OBJECTS else np.nan})
    return pd.DataFrame(rows)


def percentile_score(rates: pd.DataFrame, shell_km: int, col: str = "rate_per_1000") -> float | None:
    """1.0 if the chosen shell has the lowest near-miss rate of all valid shells, 0.0 if the highest, ties half."""
    valid = rates.dropna(subset=[col])
    row = valid[valid.shell_km == shell_km]
    if row.empty or len(valid) < 2:
        return None
    r = float(row[col].iloc[0])
    worse = (valid[col] > r).sum()
    ties = (valid[col] == r).sum() - 1
    return float((worse + 0.5 * ties) / (len(valid) - 1))
