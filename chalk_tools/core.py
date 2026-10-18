"""Tool logic for the orbit agent. Pure Python over the CelesTrak files, no Chalk imports.

The Chalk functions in chalk_tools/functions.py are thin wrappers over this module, so the same code
is unit tested locally and served on Chalk. Every tool returns the same envelope:
    {ok, data, coverage, caveats, snapshot_id}  or  {ok: False, error: {type, message}, snapshot_id}

Inputs (from pipeline/fetch_orbits.py): data/raw/celestrak/satcat.csv, socrates-minrange.csv
All counts use SATCAT mean altitude = (apogee + perigee) / 2, the same rule as pipeline/leo_shells.py.
"""
from __future__ import annotations

import hashlib
import math
import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/celestrak"

EARTH_RADIUS_KM = 6371.0
SHELL_KM = 50
MIN_ALT_KM = 200
MAX_ALT_KM = 2000
TYPE_KEYS = ("PAY", "DEB", "R/B", "UNK")
TYPE_NAMES = {"PAY": "payload", "DEB": "debris", "R/B": "rocket body", "UNK": "unknown"}
# Same list as pipeline/build_objects.py; keep the two in sync.
CONSTELLATION_PREFIXES = ("STARLINK", "ONEWEB", "KUIPER", "QIANFAN", "GUOWANG",
                          "IRIDIUM", "GLOBALSTAR", "FLOCK", "LEMUR")
# What a user can say they are launching -> CelesTrak group files (or one NORAD id for the ISS).
# Labels are CelesTrak's, not ours; see docs/object-kinds-findings.md for why "station" is the ISS alone.
KINDS = {
    "station": {"label": "space station", "norad": [25544]},
    "starlink": {"label": "Starlink-style communications constellation", "group": "starlink"},
    "oneweb": {"label": "OneWeb-style communications constellation", "group": "oneweb"},
    "kuiper": {"label": "Kuiper-style communications constellation", "group": "kuiper"},
    "earth_imaging": {"label": "Earth imaging (Planet)", "group": "planet"},
    "weather": {"label": "weather satellite", "group": "weather"},
    "cubesat": {"label": "cubesat", "group": "cubesat"},
    "science": {"label": "science satellite", "group": "science"},
    "military": {"label": "military satellite", "group": "military"},
}
# Pairs with almost no relative speed fly together (same launch, docked); not near misses.
MIN_RELATIVE_SPEED_KM_S = 0.1
# SOCRATES shows probability 1.0 on rows we cannot trust; flag, never hide or reinterpret.
SUSPECT_PROBABILITY = 0.99


def constellation(name: str) -> str | None:
    upper = str(name).upper()
    for prefix in CONSTELLATION_PREFIXES:
        if upper.startswith(prefix):
            return prefix.lower()
    return None


def load_kind_members(raw_dir: Path = RAW) -> dict:
    """kind key -> NORAD ids, from the CelesTrak group files already downloaded."""
    out: dict = {}
    for key, spec in KINDS.items():
        if "norad" in spec:
            out[key] = list(spec["norad"])
        else:
            path = raw_dir / f"{spec['group']}.json"
            out[key] = [int(o["NORAD_CAT_ID"]) for o in json.loads(path.read_text())] if path.exists() else []
    return out


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class Snapshot:
    """The data every tool reads, plus an id that changes whenever the raw files change."""
    catalog: pd.DataFrame
    socrates: pd.DataFrame
    snapshot_id: str
    kind_members: dict = field(default_factory=dict)  # kind key -> list of NORAD ids

    @classmethod
    def load(cls, raw_dir: Path = RAW) -> "Snapshot":
        satcat = raw_dir / "satcat.csv"
        socrates = raw_dir / "socrates-minrange.csv"
        d = pd.read_csv(satcat)
        d = d[d.DECAY_DATE.isna() & (d.ORBIT_CENTER == "EA")].copy()
        d["mean_alt"] = (d.APOGEE + d.PERIGEE) / 2
        d["type"] = d.OBJECT_TYPE.where(d.OBJECT_TYPE.isin(TYPE_KEYS), "UNK")
        d["launch_year"] = pd.to_datetime(d.LAUNCH_DATE, errors="coerce").dt.year
        sid = hashlib.sha256((_file_hash(satcat) + _file_hash(socrates)).encode()).hexdigest()[:12]
        return cls(catalog=d.reset_index(drop=True), socrates=pd.read_csv(socrates), snapshot_id=sid,
                   kind_members=load_kind_members(raw_dir))

    @classmethod
    def load_compact(cls, tools_dir: Path) -> "Snapshot":
        """Load the small files written by pipeline/build_tools_data.py (what ships to Chalk)."""
        kinds_file = tools_dir / "kinds.csv.gz"
        members: dict = {}
        if kinds_file.exists():
            for r in pd.read_csv(kinds_file).itertuples():
                members.setdefault(r.kind, []).append(int(r.NORAD_CAT_ID))
        return cls(catalog=pd.read_csv(tools_dir / "catalog.csv.gz"),
                   socrates=pd.read_csv(tools_dir / "socrates.csv.gz"),
                   snapshot_id=(tools_dir / "snapshot_id.txt").read_text().strip(), kind_members=members)

    @cached_property
    def approaches(self) -> pd.DataFrame:
        """SOCRATES rows after the filters, joined to each object's mean altitude."""
        s = self.socrates.copy()
        c1 = s.OBJECT_NAME_1.map(constellation)
        c2 = s.OBJECT_NAME_2.map(constellation)
        s = s[~((c1 == c2) & c1.notna()) & (s.TCA_RELATIVE_SPEED > MIN_RELATIVE_SPEED_KM_S)]
        alt = self.catalog.set_index("NORAD_CAT_ID").mean_alt
        s = s.assign(alt_1=s.NORAD_CAT_ID_1.map(alt), alt_2=s.NORAD_CAT_ID_2.map(alt))
        s["pair_alt"] = (s.alt_1 + s.alt_2) / 2
        return s.sort_values(["TCA_RANGE", "NORAD_CAT_ID_1"]).reset_index(drop=True)


def _num(v):
    """JSON-safe number: numpy to python, NaN to None."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, np.generic):
        v = v.item()
    return None if isinstance(v, float) and math.isnan(v) else v


def _ok(snap: Snapshot, data: dict, coverage: dict, caveats: list[str]) -> dict:
    return {"ok": True, "data": data, "coverage": coverage, "caveats": caveats,
            "snapshot_id": snap.snapshot_id}


def _fail(snap: Snapshot, kind: str, message: str) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message}, "snapshot_id": snap.snapshot_id}


def _bad_altitude(snap: Snapshot, altitude_km, name: str = "altitude_km"):
    if not isinstance(altitude_km, (int, float)) or isinstance(altitude_km, bool) or math.isnan(altitude_km):
        return _fail(snap, "invalid_argument", f"{name} must be a number.")
    if not MIN_ALT_KM <= altitude_km < MAX_ALT_KM:
        return _fail(snap, "out_of_range",
                     f"{name} must be {MIN_ALT_KM} to {MAX_ALT_KM:,} km. This view covers low Earth orbit only.")
    return None


def _bad_inclination(snap: Snapshot, inclination_deg):
    if (not isinstance(inclination_deg, (int, float)) or isinstance(inclination_deg, bool)
            or math.isnan(inclination_deg) or not 0 <= inclination_deg <= 180):
        return _fail(snap, "invalid_argument", "inclination_deg must be a number from 0 to 180.")
    return None


def _coverage(snap: Snapshot) -> dict:
    c = snap.catalog
    has = c.APOGEE.notna() & c.PERIGEE.notna() & c.INCLINATION.notna()
    return {"objects_in_orbit": int(len(c)), "objects_with_elements": int(has.sum()),
            "source": "CelesTrak SATCAT (tracked objects only)"}


def shell_volume_km3(lo_km: float, hi_km: float) -> float:
    return 4 / 3 * math.pi * ((EARTH_RADIUS_KM + hi_km) ** 3 - (EARTH_RADIUS_KM + lo_km) ** 3)


def shell_crowding(snap: Snapshot, altitude_km: float, inclination_deg: float | None = None,
                   inclination_band_deg: float = 10.0) -> dict:
    """Objects by type in the 50 km shell holding altitude_km, optionally near one inclination."""
    err = _bad_altitude(snap, altitude_km)
    if err:
        return err
    if inclination_deg is not None:
        err = _bad_inclination(snap, inclination_deg)
        if err:
            return err
    lo = int(math.floor(altitude_km / SHELL_KM) * SHELL_KM)
    hi = lo + SHELL_KM
    c = snap.catalog
    inshell = c[(c.mean_alt >= lo) & (c.mean_alt < hi)]
    if inclination_deg is not None:
        inshell = inshell[(inshell.INCLINATION - inclination_deg).abs() <= inclination_band_deg]
    counts = {k: int((inshell.type == k).sum()) for k in TYPE_KEYS}
    total = sum(counts.values())
    majority = max(counts, key=counts.get) if total else None
    data = {
        "shell_km": [lo, hi],
        "inclination_filter": None if inclination_deg is None
        else {"inclination_deg": inclination_deg, "band_deg": inclination_band_deg},
        "counts": counts,
        "total": total,
        "majority_type": TYPE_NAMES[majority] if majority and counts[majority] / total >= 0.5 else
        ("mixed" if total else None),
        "objects_per_million_km3": round(total / shell_volume_km3(lo, hi) * 1e6, 4),
    }
    caveats = [
        "Altitude is the average of apogee and perigee, so an object on an elliptical orbit is counted only "
        "in its average shell.",
        "Tracked objects only; small debris is not in the catalog.",
    ]
    if total == 0:
        caveats.append("No tracked objects match in this shell.")
    return _ok(snap, data, _coverage(snap), caveats)


def objects_near(snap: Snapshot, altitude_km: float, inclination_deg: float, limit: int = 10,
                 inclination_tol_deg: float = 5.0) -> dict:
    """Objects whose orbit passes through altitude_km at a similar inclination, nearest first.

    This compares orbit shapes, not positions: it says who shares your altitude and plane, not who is
    at a particular spot right now.
    """
    err = _bad_altitude(snap, altitude_km) or _bad_inclination(snap, inclination_deg)
    if err:
        return err
    limit = max(1, min(int(limit), 50))
    c = snap.catalog
    m = c[(c.PERIGEE <= altitude_km) & (c.APOGEE >= altitude_km)
          & ((c.INCLINATION - inclination_deg).abs() <= inclination_tol_deg)].copy()
    m["d_alt"] = (m.mean_alt - altitude_km).abs()
    m["d_inc"] = (m.INCLINATION - inclination_deg).abs()
    m["score"] = np.hypot(m.d_alt / SHELL_KM, m.d_inc / inclination_tol_deg)
    m = m.sort_values(["score", "NORAD_CAT_ID"])
    counts = {k: int((m.type == k).sum()) for k in TYPE_KEYS}
    objects = [{
        "norad": int(r.NORAD_CAT_ID), "name": r.OBJECT_NAME, "type": TYPE_NAMES[r.type],
        "owner": _num(r.OWNER) if isinstance(r.OWNER, float) else r.OWNER,
        "launch_year": None if pd.isna(r.launch_year) else int(r.launch_year),
        "perigee_km": _num(r.PERIGEE), "apogee_km": _num(r.APOGEE), "inclination_deg": _num(r.INCLINATION),
    } for r in m.head(limit).itertuples()]
    data = {"query": {"altitude_km": altitude_km, "inclination_deg": inclination_deg,
                      "inclination_tol_deg": inclination_tol_deg},
            "total_matches": int(len(m)), "counts": counts, "objects": objects}
    caveats = [
        "Matches share your altitude and orbital plane angle; this is not a distance or collision estimate.",
        "Tracked objects only; small debris is not in the catalog.",
        "An object on an elliptical orbit can appear here even though shell_crowding counts it in a different shell.",
    ]
    if not len(m):
        caveats.append("No tracked objects match.")
    return _ok(snap, data, _coverage(snap), caveats)


def close_approaches(snap: Snapshot, min_altitude_km: float, max_altitude_km: float, limit: int = 10) -> dict:
    """Closest predicted approaches (SOCRATES) whose two objects average inside the altitude band."""
    err = _bad_altitude(snap, min_altitude_km, "min_altitude_km") or _bad_altitude(snap, max_altitude_km, "max_altitude_km")
    if err:
        return err
    if min_altitude_km > max_altitude_km:
        return _fail(snap, "invalid_argument", "min_altitude_km must not be larger than max_altitude_km.")
    limit = max(1, min(int(limit), 50))
    a = snap.approaches
    m = a[(a.pair_alt >= min_altitude_km) & (a.pair_alt <= max_altitude_km)]
    rows = [{
        "norad_1": int(r.NORAD_CAT_ID_1), "name_1": r.OBJECT_NAME_1,
        "norad_2": int(r.NORAD_CAT_ID_2), "name_2": r.OBJECT_NAME_2,
        "tca_utc": r.TCA, "miss_distance_m": round(float(r.TCA_RANGE) * 1000, 1),
        "relative_speed_km_s": float(r.TCA_RELATIVE_SPEED),
        "max_probability": float(r.MAX_PROB),
        "probability_flag": "suspect" if r.MAX_PROB >= SUSPECT_PROBABILITY else None,
        "pair_altitude_km": round(float(r.pair_alt), 1),
    } for r in m.head(limit).itertuples()]
    s = snap.socrates
    data = {"window_utc": [str(s.TCA.min()), str(s.TCA.max())], "rows_available": int(len(m)), "approaches": rows}
    caveats = [
        "These are CelesTrak SOCRATES predictions for one week, not events that have happened.",
        "max_probability is SOCRATES's own number; quote it only as SOCRATES's.",
        "Same-constellation pairs and objects flying together (relative speed under 0.1 km/s) are removed.",
    ]
    if any(r["probability_flag"] for r in rows):
        caveats.append("A row marked suspect shows SOCRATES probability near 1.0, which we cannot verify.")
    if not len(m):
        caveats.append("No predicted close approaches in this altitude band.")
    return _ok(snap, data, _coverage(snap), caveats)


def crossing_count(snap: Snapshot, lo_km: float, hi_km: float, inclination_deg: float, band_deg: float) -> int:
    """Tracked objects whose orbit passes through [lo_km, hi_km) at inclination within band_deg."""
    c = snap.catalog
    return int(((c.PERIGEE < hi_km) & (c.APOGEE >= lo_km) & ((c.INCLINATION - inclination_deg).abs() <= band_deg)).sum())


def _time_fraction(perigee_alt_km, apogee_alt_km, lo_km: float, hi_km: float):
    """Fraction of each orbit spent between lo_km and hi_km altitude (Kepler's equation, Earth-centered).

    Takes arrays of perigee and apogee altitudes. Near-circular orbits count fully in the shell holding their
    average altitude. This is what turns 'passes through the shell' into 'is in the shell at a random moment'.
    """
    rp = EARTH_RADIUS_KM + np.asarray(perigee_alt_km, dtype=float)
    ra = EARTH_RADIUS_KM + np.asarray(apogee_alt_km, dtype=float)
    a = (rp + ra) / 2
    e = (ra - rp) / (ra + rp)
    circular = e < 1e-4
    safe_e = np.where(circular, 1.0, e)

    def mean_anomaly(r):
        cos_ea = np.clip((1 - (EARTH_RADIUS_KM + r) / a) / safe_e, -1, 1)
        ea = np.arccos(cos_ea)
        return ea - e * np.sin(ea)

    frac = (mean_anomaly(hi_km) - mean_anomaly(lo_km)) / np.pi
    mid = a - EARTH_RADIUS_KM
    return np.where(circular, ((mid >= lo_km) & (mid < hi_km)).astype(float), np.clip(frac, 0, 1))


def shell_occupancy(snap: Snapshot, lo_km: float, hi_km: float, inclination_deg: float, band_deg: float) -> float:
    """Expected number of tracked objects inside [lo_km, hi_km) at a random moment, near one inclination."""
    c = snap.catalog.dropna(subset=["APOGEE", "PERIGEE", "INCLINATION"])
    c = c[(c.INCLINATION - inclination_deg).abs() <= band_deg]
    c = c[(c.PERIGEE < hi_km) & (c.APOGEE >= lo_km)]
    return float(_time_fraction(c.PERIGEE.values, c.APOGEE.values, lo_km, hi_km).sum())


def recommend_orbit(snap: Snapshot, inclination_deg: float, min_altitude_km: float = 400.0,
                    max_altitude_km: float = 1200.0, top_n: int = 5, inclination_band_deg: float = 10.0) -> dict:
    """Rank 50 km shells in a band, quietest first, for a given inclination.

    The ranking is the crowding index only: the expected number of tracked objects inside the shell at a random
    moment, near this inclination, counting each object for the share of its orbit spent in the shell (fewest
    first; ties go to the lower shell). A plain count of orbits that merely cross the shell was tried first and
    rejected: elongated orbits cross every shell but spend almost no time in any. It never reads SOCRATES, so SOCRATES can
    be used to test whether the index means anything. Quiet means few tracked objects, not safe.
    """
    err = (_bad_altitude(snap, min_altitude_km, "min_altitude_km") or _bad_altitude(snap, max_altitude_km, "max_altitude_km")
           or _bad_inclination(snap, inclination_deg))
    if err:
        return err
    if min_altitude_km >= max_altitude_km:
        return _fail(snap, "invalid_argument", "min_altitude_km must be smaller than max_altitude_km.")
    top_n = max(1, min(int(top_n), 10))
    lo0 = int(math.floor(min_altitude_km / SHELL_KM) * SHELL_KM)
    hi0 = int(math.ceil(max_altitude_km / SHELL_KM) * SHELL_KM)
    rows = []
    for lo in range(lo0, hi0, SHELL_KM):
        hi = lo + SHELL_KM
        here = shell_crowding(snap, lo, inclination_deg, inclination_band_deg)["data"]
        rows.append({
            "shell_km": [lo, hi],
            "expected_objects": round(shell_occupancy(snap, lo, hi, inclination_deg, inclination_band_deg), 1),
            "crossing_objects": crossing_count(snap, lo, hi, inclination_deg, inclination_band_deg),
            "objects_in_shell": here["total"],
            "objects_per_million_km3": here["objects_per_million_km3"],
            "debris_share": round(here["counts"]["DEB"] / here["total"], 3) if here["total"] else None,
            "majority_type": here["majority_type"],
        })
    ranked = sorted(rows, key=lambda r: (r["expected_objects"], r["shell_km"][0]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    data = {
        "query": {"inclination_deg": inclination_deg, "inclination_band_deg": inclination_band_deg,
                  "altitude_range_km": [lo0, hi0]},
        "candidates": ranked[:top_n],
        "busiest": ranked[-1],
        "shells_ranked": len(ranked),
    }
    caveats = [
        "Quietest means the fewest tracked objects expected in that shell at a similar inclination. It is not a guarantee of safety.",
        "Ranked by crowding only; it ignores how long debris stays in orbit, which depends on altitude and is not modeled here.",
        "Tracked objects only; small debris is not in the catalog.",
    ]
    if any(c["shell_km"][0] < 400 for c in ranked[:top_n]):
        caveats.append("Shells below about 400 km look quiet partly because atmospheric drag pulls objects down quickly; "
                       "a satellite placed there would be pulled down too.")
    if any((c["debris_share"] or 0) >= 0.5 for c in ranked[:top_n]):
        caveats.append("Some quiet shells are mostly debris (see debris_share); few objects there does not mean a clean shell.")
    return _ok(snap, data, _coverage(snap), caveats)


def launch_kind_profile(snap: Snapshot, kind: str) -> dict:
    """What existing objects of one kind look like: where they fly and how many close approaches they see.

    The orbit numbers (altitude, inclination) are what real objects of that kind do today, so they work as a
    starting point for a launch. The close-approach number is observed for those objects, one week of SOCRATES;
    it is not a forecast for a new satellite and not a collision probability.
    """
    spec = KINDS.get(kind)
    if spec is None:
        return _fail(snap, "unknown_kind", f"kind must be one of: {', '.join(KINDS)}.")
    ids = snap.kind_members.get(kind, [])
    c = snap.catalog
    m = c[c.NORAD_CAT_ID.isin(ids) & (c.mean_alt >= MIN_ALT_KM) & (c.mean_alt < MAX_ALT_KM)]
    if m.empty:
        return _fail(snap, "no_data", f"No low-orbit objects of kind '{kind}' in this snapshot.")
    a = snap.approaches
    events = pd.concat([a.NORAD_CAT_ID_1, a.NORAD_CAT_ID_2]).value_counts()
    per_obj = m.NORAD_CAT_ID.map(events).fillna(0)
    alt_med = float(m.mean_alt.median())
    shell = shell_crowding(snap, alt_med)["data"]
    data = {
        "kind": kind, "label": spec["label"],
        "objects": int(len(m)),
        "altitude_km": {"p10": round(float(m.mean_alt.quantile(0.1))), "median": round(alt_med),
                        "p90": round(float(m.mean_alt.quantile(0.9)))},
        "inclination_deg_median": round(float(m.INCLINATION.median()), 1),
        "close_approaches_per_object": round(float(per_obj.mean()), 1),
        "share_with_at_least_one": round(float((per_obj > 0).mean()), 2),
        "shell_at_median_altitude": {
            "shell_km": shell["shell_km"], "objects_in_shell": shell["total"],
            "debris_share": round(shell["counts"]["DEB"] / shell["total"], 2) if shell["total"] else None},
        "all_leo_close_approaches_per_object": round(float(
            c[(c.mean_alt >= MIN_ALT_KM) & (c.mean_alt < MAX_ALT_KM)].NORAD_CAT_ID.map(events).fillna(0).mean()), 1),
    }
    caveats = [
        "Close approaches are SOCRATES predictions for one week, per existing object of this kind. They are not "
        "collision probabilities and not a forecast for a new satellite.",
        "SOCRATES only lists pairs that include an active satellite, and same-constellation pairs are removed here, "
        "so constellations look quieter than other kinds partly by construction.",
        "Near-polar orbits (about 97 degrees) cross many inclined constellations; that may explain high counts "
        "for imaging, weather, cubesat and science kinds, but it was not tested.",
        "Kind labels are CelesTrak's group files; tracked objects only.",
    ]
    if kind == "station":
        caveats.append("Space station means the ISS alone (one object), so its numbers are an example, not a statistic.")
    if len(m) < 30:
        caveats.append(f"Only {len(m)} objects of this kind; treat the averages loosely.")
    return _ok(snap, data, _coverage(snap), caveats)
