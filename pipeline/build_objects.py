"""Join orbits + catalog info into the files the frontend reads.

Inputs (from pipeline/fetch_orbits.py): data/raw/celestrak/*.json, satcat.csv, socrates-minrange.csv
Outputs:
  data/out/objects.json          every object we have an orbit for: OMM elements (feed straight into
                                 satellite.js json2satrec) + type, owner, launch date, radar size, group
  data/out/close_approaches.json the 500 closest predicted approaches in the next 7 days, with pairs from
                                 the same constellation removed
Run from the repo root: uv run python pipeline/build_objects.py
"""
import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/celestrak"
OUT = ROOT / "data/out"
LABEL_GROUPS = ["stations", "starlink", "oneweb", "kuiper", "qianfan", "hulianwang", "planet",
                "cubesat", "education", "geo", "gnss", "weather", "science", "military"]
DEBRIS_GROUPS = ["fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris", "cosmos-1408-debris"]
SOURCE_GROUPS = ["active", "analyst", "last-30-days"] + DEBRIS_GROUPS
TYPE_NAMES = {"PAY": "satellite", "DEB": "debris", "R/B": "rocket body", "UNK": "unknown"}


def load(group):
    p = RAW / f"{group}.json"
    return json.loads(p.read_text()) if p.exists() else []


def constellation(name):
    for prefix in ("STARLINK", "ONEWEB", "KUIPER", "QIANFAN", "GUOWANG", "IRIDIUM", "GLOBALSTAR", "FLOCK", "LEMUR"):
        if name.upper().startswith(prefix):
            return prefix.lower()
    return None


def main():
    orbits, source = {}, {}
    for g in SOURCE_GROUPS:
        for o in load(g):
            orbits.setdefault(o["NORAD_CAT_ID"], o)
            source.setdefault(o["NORAD_CAT_ID"], g)
    labels = {}
    for g in LABEL_GROUPS:
        for o in load(g):
            labels.setdefault(o["NORAD_CAT_ID"], []).append(g)

    cat = pd.read_csv(RAW / "satcat.csv").set_index("NORAD_CAT_ID")
    objects = []
    for nid, omm in orbits.items():
        row = cat.loc[nid] if nid in cat.index else None
        def field(col):
            if row is None or pd.isna(row[col]):
                return None
            v = row[col]
            return v.item() if hasattr(v, "item") else v
        otype = field("OBJECT_TYPE")
        objects.append({
            "norad": nid,
            "name": omm["OBJECT_NAME"],
            "type": TYPE_NAMES.get(otype, "unknown"),
            "owner": field("OWNER"),
            "launch_date": field("LAUNCH_DATE"),
            "radar_size_m2": field("RCS"),
            "apogee_km": field("APOGEE"),
            "perigee_km": field("PERIGEE"),
            "constellation": constellation(omm["OBJECT_NAME"]),
            "groups": labels.get(nid, []),
            "source_group": source[nid],
            "omm": omm,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "objects.json").write_text(json.dumps({
        "source": "CelesTrak GP (OMM) + SATCAT, see pipeline/fetch_orbits.py",
        "count": len(objects),
        "objects": objects,
    }))
    print(f"objects.json: {len(objects)} objects, "
          + ", ".join(f"{t}: {sum(o['type'] == t for o in objects)}" for t in TYPE_NAMES.values()))

    s = pd.read_csv(RAW / "socrates-minrange.csv")
    c1 = s.OBJECT_NAME_1.map(lambda n: constellation(str(n)))
    c2 = s.OBJECT_NAME_2.map(lambda n: constellation(str(n)))
    # Pairs with almost no relative speed are objects flying together (same launch, docked), not near misses.
    s = s[~((c1 == c2) & c1.notna()) & (s.TCA_RELATIVE_SPEED > 0.1)].sort_values("TCA_RANGE").head(500)
    rows = [{
        "norad_1": int(r.NORAD_CAT_ID_1), "name_1": r.OBJECT_NAME_1,
        "norad_2": int(r.NORAD_CAT_ID_2), "name_2": r.OBJECT_NAME_2,
        "time_utc": r.TCA, "miss_distance_km": float(r.TCA_RANGE),
        "relative_speed_km_s": float(r.TCA_RELATIVE_SPEED), "max_probability": float(r.MAX_PROB),
    } for r in s.itertuples()]
    (OUT / "close_approaches.json").write_text(json.dumps({
        "source": "CelesTrak SOCRATES sort-minRange.csv, same-constellation pairs removed",
        "rows": rows,
    }, indent=1))
    print(f"close_approaches.json: {len(rows)} rows, closest {rows[0]['miss_distance_km']} km "
          f"({rows[0]['name_1']} vs {rows[0]['name_2']})")


if __name__ == "__main__":
    main()
