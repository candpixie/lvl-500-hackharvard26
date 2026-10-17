"""How crowded each 50 km shell of low Earth orbit is, by object type -> data/out/leo_shells.json

Source: CelesTrak SATCAT (data/raw/celestrak/satcat.csv from fetch_orbits.py).
Counts objects with no decay date orbiting Earth. Altitude = (apogee + perigee) / 2, a shell average.
"""
import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    d = pd.read_csv(ROOT / "data/raw/celestrak/satcat.csv")
    on = d[d.DECAY_DATE.isna() & (d.ORBIT_CENTER == "EA")].copy()
    on["alt"] = (on.APOGEE + on.PERIGEE) / 2
    leo = on[on.alt < 2000].assign(shell=lambda x: (x.alt // 50 * 50).astype(int))
    t = leo.pivot_table(index="shell", columns="OBJECT_TYPE", values="NORAD_CAT_ID", aggfunc="count", fill_value=0)
    rows = [{"shell_km": int(s), **{k: int(v) for k, v in r.items()}} for s, r in t.iterrows()]
    (ROOT / "data/out/leo_shells.json").write_text(json.dumps({
        "source": "CelesTrak SATCAT, objects with no decay date, Earth-centered, mean altitude=(apogee+perigee)/2",
        "types": {"PAY": "payload", "DEB": "debris", "R/B": "rocket body", "UNK": "unknown"},
        "shells": rows,
    }, indent=1))
    print(f"{len(on)} objects in orbit, {len(leo)} in LEO, {len(rows)} shells")


if __name__ == "__main__":
    main()
