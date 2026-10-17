"""Write the small files the Chalk tool functions read -> data/out/tools/ (gitignored)

Keeps only the columns the tools use, from the same raw CelesTrak files and with the same snapshot id,
so a function deployed to Chalk answers from exactly the data the local tests checked.
Run after fetch_orbits.py:  uv run python pipeline/build_tools_data.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chalk_tools import core  # noqa: E402

OUT = ROOT / "data/out/tools"
CATALOG_COLS = ["NORAD_CAT_ID", "OBJECT_NAME", "OWNER", "APOGEE", "PERIGEE", "INCLINATION",
                "mean_alt", "type", "launch_year"]
SOCRATES_COLS = ["NORAD_CAT_ID_1", "OBJECT_NAME_1", "NORAD_CAT_ID_2", "OBJECT_NAME_2",
                 "TCA", "TCA_RANGE", "TCA_RELATIVE_SPEED", "MAX_PROB"]


def main():
    snap = core.Snapshot.load()
    OUT.mkdir(parents=True, exist_ok=True)
    snap.catalog[CATALOG_COLS].to_csv(OUT / "catalog.csv.gz", index=False)
    snap.socrates[SOCRATES_COLS].to_csv(OUT / "socrates.csv.gz", index=False)
    (OUT / "snapshot_id.txt").write_text(snap.snapshot_id)
    sizes = {p.name: f"{p.stat().st_size / 1e6:.1f} MB" for p in OUT.iterdir()}
    print(f"snapshot {snap.snapshot_id}: {sizes}")


if __name__ == "__main__":
    main()
