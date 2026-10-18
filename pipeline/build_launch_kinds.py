"""Write web/public/launch_kinds.json: one row per kind of object a user can say they are launching.

Same numbers as chalk_tools.core.launch_kind_profile (the Chalk tool), computed from the same raw files, so the
picker in the UI and the agent agree. Run after fetch_orbits.py:  uv run python pipeline/build_launch_kinds.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chalk_tools import core  # noqa: E402

OUT = ROOT / "web/public/launch_kinds.json"
GRID = ROOT / "data/out/crowding_grid.json"


def band_grid():
    """Tracked objects per 50 km shell and 10 degree inclination band, so the picker can say how many of a shell's
    objects share your inclination. Same table the team's heatmap and place ranking use (time spread evenly
    between perigee and apogee), so it is a lower bound."""
    rows = json.loads(GRID.read_text())["rows"]
    alts = sorted({r["alt_lo"] for r in rows})
    incs = sorted({r["inc_lo"] for r in rows})
    index = {(r["alt_lo"], r["inc_lo"]): r for r in rows}
    return {
        "alt_lo": alts, "alt_step_km": 50, "inc_lo": incs, "inc_step_deg": 10,
        "total": [[round(index[a, i]["total"]) for i in incs] for a in alts],
        "shell_total": [round(sum(index[a, i]["total"] for i in incs)) for a in alts],  # add first, then round
        "debris": [[round(index[a, i]["DEB"]) for i in incs] for a in alts],
        "note": "tracked objects only, a lower bound; time spread evenly between perigee and apogee",
    }


def main():
    snap = core.Snapshot.load()
    kinds = []
    for key in core.KINDS:
        res = core.launch_kind_profile(snap, key)
        if res["ok"]:
            kinds.append(res["data"] | {"caveats": res["caveats"]})
    payload = {"snapshot_id": snap.snapshot_id, "source": "CelesTrak SATCAT + SOCRATES, one week", "kinds": kinds}
    # the grid is two dozen rows of numbers: keep it on a few lines instead of one number per line
    OUT.write_text(json.dumps(payload, indent=1)[:-2] + ',\n "band_grid": ' + json.dumps(band_grid()) + "\n}\n")
    print(f"{len(kinds)} kinds -> {OUT} (snapshot {snap.snapshot_id})")


if __name__ == "__main__":
    main()
