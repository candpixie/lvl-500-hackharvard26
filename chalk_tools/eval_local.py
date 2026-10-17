"""Local dry run of the headline eval (the Chalk version reuses answer_key.py).

For each mission inclination, compare three pickers on the SOCRATES answer key:
  recommend_orbit (top 1)  |  fewest objects by average altitude (the web app's current rule)  |  random pick
under three candidate answer-key measures (see answer_key.shell_rates). All three are reported so the choice
of measure cannot hide a bad result.
Run: uv run python -m chalk_tools.eval_local
"""
import numpy as np
import pandas as pd

from chalk_tools import answer_key, core

INCLINATIONS = [0, 10, 20, 28.5, 35, 45, 51.6, 53, 60, 63.4, 70, 80, 87, 90, 97.5, 98, 100]
MIN_ALT, MAX_ALT, BAND = 400, 1200, 10.0
MEASURES = {"events": "raw near-miss count per shell", "rate_per_1000": "per 1,000 tracked objects",
            "rate_indep": "per 1,000 non-constellation objects"}


def main():
    snap = core.Snapshot.load()
    ev = answer_key.events(snap)
    out = {m: [] for m in MEASURES}
    for inc in INCLINATIONS:
        rates = answer_key.shell_rates(snap, ev, inc, MIN_ALT, MAX_ALT, BAND)
        cand = core.recommend_orbit(snap, inc, MIN_ALT, MAX_ALT, top_n=10, inclination_band_deg=BAND)["data"]
        rec = cand["candidates"][0]["shell_km"][0]
        by_cross = {c["shell_km"][0]: c["crossing_objects"] for c in cand["candidates"] + [cand["busiest"]]}
        for m in MEASURES:
            valid = rates.dropna(subset=[m])
            if len(valid) < 4 or rec not in set(valid.shell_km):
                continue
            naive = int(valid.sort_values(["objects", "shell_km"]).shell_km.iloc[0])
            crossing = pd.Series([core.crossing_count(snap, int(s), int(s) + 50, inc, BAND) for s in valid.shell_km])
            occ = pd.Series([core.shell_occupancy(snap, int(s), int(s) + 50, inc, BAND) for s in valid.shell_km])
            cross_pick = int(valid.shell_km.iloc[int(crossing.values.argmin())])
            out[m].append({"inc": inc, "recommend": answer_key.percentile_score(rates, rec, m),
                           "naive": answer_key.percentile_score(rates, naive, m),
                           "crossing": answer_key.percentile_score(rates, cross_pick, m),
                           "rho_occ": occ.rank().corr(valid[m].reset_index(drop=True).rank()),
                           "random": float(np.mean([answer_key.percentile_score(rates, int(s), m) for s in valid.shell_km])),
                           "rho": crossing.rank().corr(valid[m].reset_index(drop=True).rank())})
    for m, label in MEASURES.items():
        df = pd.DataFrame(out[m]); n = len(df)
        se = lambda c: df[c].std() / np.sqrt(n)
        print(f"\n== answer key: {label} ({n} missions) ==")
        print(f"recommend_orbit (time in shell) {df.recommend.mean():.3f} +/- {se('recommend'):.3f} | crossing count (rejected) {df.crossing.mean():.3f} | fewest objects by avg altitude {df.naive.mean():.3f} +/- {se('naive'):.3f} | random {df.random.mean():.3f}")
        print(f"crowding_validity Spearman: time-in-shell {df.rho_occ.mean():.3f}, crossing {df.rho.mean():.3f}; recommend beats random in {(df.recommend > df.random).sum()}/{n}")


if __name__ == "__main__":
    main()
