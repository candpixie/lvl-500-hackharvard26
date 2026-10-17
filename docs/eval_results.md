# Eval results: does recommend_orbit steer away from predicted near misses?

Data snapshot `d29cf5404f55` (CelesTrak SATCAT + SOCRATES Oct 16 to 23, 2026). Written by Person A. Numbers are from real runs.

## What was measured
For each mission (an inclination and an altitude band), a picker chooses one 50 km shell. The score is where that shell ranks among the band's shells by SOCRATES predicted near-miss count: 1.0 = fewest near misses, 0.0 = most, random = 0.5. The picker never sees SOCRATES. Pickers: `recommend` (recommend_orbit, top 1), `count_in_plane` (fewest objects by average altitude near the same inclination), `web_rule` (the web app's rule: fewest objects by average altitude, any inclination), `random`.

## Run 1 on Chalk (evaluation `recommend-orbit-vs-baselines`, run `08b38637-3468-4a62-83eb-5f0a13b497f8`)
17 inclinations, band 400 to 1200 km, 221 rows, 0 task errors, 0 scorer errors. Identical to the local dry run.

| Picker | Mean score |
|---|---|
| web_rule | 0.904 (always picks 1,000 km) |
| recommend | 0.851 +/- 0.041 |
| count_in_plane | 0.839 +/- 0.033 |
| random (10 seeds) | 0.505 |

## Local runs over realistic mission bands (same code and data)
| Band | recommend | count_in_plane | web_rule | random |
|---|---|---|---|---|
| 400-1200 km | 0.851 | 0.839 | 0.904 | 0.500 |
| 400-600 km | 0.941 | 0.941 | 1.000 | 0.500 |
| 500-800 km | 0.606 | 0.618 | 0.753 | 0.500 |
| 600-900 km | 0.476 | 0.453 | 0.447 | 0.500 |

## What this does and does not show
- The crowding index tracks where predicted near misses happen across LEO: rank correlation +0.71 between time-in-shell and near-miss count (the first version, counting orbits that merely cross a shell, scored 0.53 and correlated -0.23, so it was replaced; the key's inclination definition also had a bug that was fixed).
- It beats random across the full range (16 of 17 missions) but does NOT beat simple rules: web_rule and count_in_plane tie or win in every band, and in the 600 to 900 km band recommend_orbit is no better than random.
- The key mostly rewards leaving the Starlink-dominated 450 to 600 km shells. A constant "pick a high shell" or "pick the lowest shell" can score well depending on the band, so this eval cannot show that the inclination-aware ranking is better.
- Per-object near-miss rates scored below random for every picker (quiet shells show higher rates per object); we do not trust them and do not report them as a headline.
- The key has limits: SOCRATES covers one week, only pairs with at least one active satellite, and has no altitude, so events are assigned by the pair's average altitude.
- The ranking was changed twice after seeing results, for physical and definitional reasons (above), not by tuning on the score. State this plainly if asked.
- Safe claims for the demo: "the index predicts where predicted near misses cluster across low Earth orbit (rank correlation 0.71)" and "we tested it against SOCRATES and against simple rules, and here is where it does and does not help." Do not claim it beats simple rules, or that any shell is safe.

## Reproduce
Local: `uv run python -m chalk_tools.eval_local`. On Chalk: `uv run --with chalkcompute --with chalkpy python -m chalk_tools.run_eval` (deploys `pick_orbit` and `shell_safety`, uploads a dataset, runs the evaluation).
