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
from dataclasses import dataclass
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
        return cls(catalog=d.reset_index(drop=True), socrates=pd.read_csv(socrates), snapshot_id=sid)

    @classmethod
    def load_compact(cls, tools_dir: Path) -> "Snapshot":
        """Load the small files written by pipeline/build_tools_data.py (what ships to Chalk)."""
        return cls(catalog=pd.read_csv(tools_dir / "catalog.csv.gz"),
                   socrates=pd.read_csv(tools_dir / "socrates.csv.gz"),
                   snapshot_id=(tools_dir / "snapshot_id.txt").read_text().strip())

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
