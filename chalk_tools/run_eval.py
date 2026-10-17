"""Create and run the headline eval on Chalk, then print mean shell_safety per picker.

    uv run --with chalkcompute --with chalkpy python -m chalk_tools.run_eval

Missions are inclinations; the answer key (SOCRATES near-miss count per shell, from every row of the weekly file)
is built here from the raw files and travels only in the dataset, never to the task.
"""
import json
import sys

import chalkcompute

from chalk_tools import answer_key, core
from chalk_tools.eval_functions import pick_orbit, shell_safety

INCLINATIONS = [0, 10, 20, 28.5, 35, 45, 51.6, 53, 60, 63.4, 70, 80, 87, 90, 97.5, 98, 100]
BANDS = [(400.0, 1200.0), (400.0, 600.0), (500.0, 800.0), (600.0, 900.0)]  # full range plus realistic mission bands
BAND = 10.0
RANDOM_SEEDS = range(10)
NAME = "recommend-orbit-vs-baselines-v2"  # v1 was the single 400-1200 km band


def build_rows(snap):
    ev = answer_key.events(snap)
    rows = []
    for lo, hi in BANDS:
        for inc in INCLINATIONS:
            rates = answer_key.shell_rates(snap, ev, inc, lo, hi, BAND)
            key = json.dumps({str(int(r.shell_km)): int(r.events) for r in rates.itertuples()})
            base = {"mission": f"inc{inc}_{int(lo)}-{int(hi)}", "band": f"{int(lo)}-{int(hi)}", "inclination_deg": float(inc),
                    "min_altitude_km": lo, "max_altitude_km": hi, "inclination_band_deg": BAND, "events_by_shell": key}
            for picker in ("recommend", "count_in_plane", "web_rule"):
                rows.append({**base, "picker": picker, "seed": 0})
            for s in RANDOM_SEEDS:
                rows.append({**base, "picker": "random", "seed": s})
    return rows


def main():
    snap = core.Snapshot.load()
    rows = build_rows(snap)
    print(f"{len(rows)} rows, snapshot {snap.snapshot_id}")
    dataset = chalkcompute.DatasetClient().upload(NAME, rows)
    evaluation = chalkcompute.Evaluation.create(NAME, dataset=dataset, task=pick_orbit, scorers=[shell_safety],
                                                metadata={"snapshot_id": snap.snapshot_id, "measure": "raw SOCRATES near-miss count per shell"})
    run = evaluation.run(metadata={"snapshot_id": snap.snapshot_id}).wait()
    print("run", run.id, run.status)
    df = chalkcompute.DatasetClient().read(run.result_dataset).to_pandas()
    print("columns:", [c for c in df.columns if not c.startswith("__chalk__")])
    # custom function scorers appear as scorer_<id>; built-in and SQL scorers as <name>_value
    score_col = next(c for c in df.columns if (c.startswith("scorer_") or c.endswith("_value")) and not c.endswith("_error"))
    err_cols = [c for c in df.columns if c.endswith("_error")]
    print("row errors:", {c: int(df[c].notna().sum()) for c in err_cols})
    print(df.groupby(["band", "picker"])[score_col].agg(["mean", "std", "count"]).round(3))
    print("run id:", run.id, "| evaluation id:", evaluation.id, file=sys.stderr)


if __name__ == "__main__":
    main()
