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


def main():
    snap = core.Snapshot.load()
    kinds = []
    for key in core.KINDS:
        res = core.launch_kind_profile(snap, key)
        if res["ok"]:
            kinds.append(res["data"] | {"caveats": res["caveats"]})
    payload = {"snapshot_id": snap.snapshot_id, "source": "CelesTrak SATCAT + SOCRATES, one week", "kinds": kinds}
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"{len(kinds)} kinds -> {OUT} (snapshot {snap.snapshot_id})")


if __name__ == "__main__":
    main()
