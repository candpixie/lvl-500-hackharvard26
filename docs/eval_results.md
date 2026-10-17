# Eval results: does recommend_orbit steer away from predicted near misses?

Data snapshot `d29cf5404f55` (CelesTrak SATCAT + SOCRATES Oct 16 to 23, 2026). Numbers are from real runs.

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

## Run 2 on Chalk (evaluation `recommend-orbit-vs-baselines-v2`, run `62f85b1c-3310-4c84-9766-1df3f7ed6f01`)
884 rows (4 bands x 17 inclinations x 13 picker rows), 0 task errors, 0 scorer errors. The table below is from this run; it matches the earlier local run in every cell.

## Bands table (Chalk run 2; same numbers as the local runs)
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

---

# Junk-band eval of the Chalk ask service (the team's eval spec)

Evaluation `ask-junk-band`, run `418294b0-b957-42ae-b8a2-e93f93575f48` on Chalk (env `spcwce09a241`). The task is the same `ask_core.answer` the live `POST /ask` endpoint serves (`docs/chalk-ask-service.md`). 58 questions: the four demo questions plus varied counts, sizes, altitudes and mission phrases. Identical to the local dry run (`uv run python -m chalk_tools.junk_eval_local`).

| Score | Result |
|---|---|
| `junk_band`: a "where should I put it" answer recommends a shell outside 750 to 850 km AND with dead-satellite lifetime under 25 years | **26 / 26** |
| `grounded`: every number spoken comes from a tool result, the tool arguments, or the question | 58 / 58 |
| `guardrails_ok`: no "safe", no "collision probability" outside a SOCRATES quote, tracked-objects wording | 58 / 58 |
| answered (no error), task errors | 58 / 58, 0 |

## Read this before quoting 26 / 26
- **It is an easy bar.** All 26 "where" questions get the same answer: focus 525 km, dead-satellite lifetime about 10.6 years. The team's `rank()` barely changes with satellite count, size or phrasing (a 4 m satellite and a 40 m one, one satellite or a million, give the same top shells 500, 550, 600), and the shell model ignores inclination. A fixed "always 525 km" answer would also score 26 / 26. The test does have teeth against naive pickers: fewest objects (1,925 km), busiest shell, fewest debris, always 800 km, and always 1,000 km all fail it.
- **What it shows:** the recommendation stays out of the debris band and favors shells where wreckage comes down within about a decade. **What it does not show:** that the recommendation responds to the question.
- **The rate and lifetime numbers are rough.** The decay table is rule-of-thumb anchors (the team's own docs say to verify against a published source before a slide).

## It points the other way from my near-miss eval
The recommended shell, 500 to 550 km, scores **0.13** (at 53 degrees) and **0.07** (at 98 degrees) on the SOCRATES near-miss key from the first eval above, where 1.0 means the fewest predicted close approaches of the 16 shells from 400 to 1,200 km. The shells with the fewest predicted close approaches are 950 to 1,150 km. These are different objectives, and both are reasonable:
- The team's score is expected harm = collision rate x years the wreckage stays up. That favors low shells where debris clears quickly, even though they are crowded.
- The near-miss key counts predicted close approaches this week (pairs including at least one active satellite, same-constellation pairs removed), which is highest around the low shells where Starlink-like constellations fly.
So the honest framing for judges is "we rank by expected harm including how long wreckage persists, not by predicted near-miss count, and here is how the two differ," not "500 km has the fewest close approaches."

## Not yet done
Monitors and a dashboard; running my tool-calling cases against the real Grok loop (`from agent import run_agent`; needs an xAI key).
