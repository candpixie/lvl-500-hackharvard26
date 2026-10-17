"""Describe the data snapshot the tools and the web app read -> data/out/manifest.json

The snapshot id is a hash of satcat.csv and socrates-minrange.csv. Every tool result and trace carries it,
so any answer can be tied to the exact data it used. Run after fetch_orbits.py and build_objects.py:
    uv run python pipeline/manifest.py
"""
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chalk_tools import core  # noqa: E402

RAW = ROOT / "data/raw/celestrak"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main():
    snap = core.Snapshot.load(RAW)
    active = json.loads((RAW / "active.json").read_text())
    epochs = pd.to_datetime([o["EPOCH"] for o in active], utc=True)
    now = datetime.now(timezone.utc)
    files = {p.name: {"sha256_16": sha(p), "bytes": p.stat().st_size} for p in sorted(RAW.glob("*")) if p.is_file()}
    objects = ROOT / "data/out/objects.json"
    manifest = {
        "snapshot_id": snap.snapshot_id,
        "built_utc": now.isoformat(timespec="seconds"),
        "catalog": {"objects_in_orbit": int(len(snap.catalog)),
                    "by_type": {k: int((snap.catalog.type == k).sum()) for k in core.TYPE_KEYS}},
        "orbits": {"objects_with_orbit_elements": json.loads(objects.read_text())["count"] if objects.exists() else None,
                   "active_epoch_newest_utc": epochs.max().isoformat(timespec="seconds"),
                   "active_epoch_median_age_hours": round(float((now - epochs).median().total_seconds() / 3600), 1)},
        "socrates": {"rows": int(len(snap.socrates)), "rows_after_filters": int(len(snap.approaches)),
                     "window_utc": [str(snap.socrates.TCA.min()), str(snap.socrates.TCA.max())]},
        "files": files,
    }
    (ROOT / "data/out/manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"manifest.json: snapshot {snap.snapshot_id}, SOCRATES window {manifest['socrates']['window_utc'][0]} "
          f"to {manifest['socrates']['window_utc'][1]}")


if __name__ == "__main__":
    main()
