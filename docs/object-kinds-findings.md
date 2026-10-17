# Does the kind of object matter? What the data and the model say

Snapshot `d29cf5404f55` (CelesTrak SATCAT and SOCRATES, Oct 16 to 23 2026). Computed Oct 17 by Person A. Two separate questions, kept separate on purpose: what the team's model *assumes* (a calculation), and what the real data *shows* (an observation).

## 1. The team's model (`pipeline/scoring.py`, `pipeline/orbit_data.py`): size changes the risk, not the best place
| Object | Expected collisions per year, 1 satellite at 550 km | Score at 550 km | Score at 900 km | Best shells (1,000 of them) |
|---|---|---|---|---|
| cubesat 0.3 m | 1.9e-05 | 74.5 | 31.9 | 500, 550, 600 |
| small sat 1 m | 4.5e-05 | 74.5 | 31.9 | 500, 550, 600 |
| medium 4x2x1 m | 2.8e-04 | 74.5 | 31.9 | 500, 550, 600 |
| large 10 m | 1.3e-03 | 74.5 | 31.9 | 500, 550, 600 |
| station-size 40 m | 1.9e-02 | 74.5 | 31.9 | 500, 550, 600 |

- The raw rate scales with cross-section: a 40 m object is about 1,000 times a cubesat. That is built into the formula (area of a circle of radius half the longest side plus 0.5 m), not measured.
- The 0 to 100 score and the ranking are **identical for every size**, because the score is normalized across shells and size multiplies every shell by the same factor. So the UI's size input changes the collisions-per-year number but never the recommendation or the score.
- Dead-satellite lifetime depends only on altitude (a rough lookup). It ignores mass and area, which in reality change decay time a lot.
- Odd, worth a look by the model's owners: the score rises with satellite count (74.5 for 1, 77.8 for a million at 550 km), because the score is relative to other shells.

## 2. The real data: type and size do matter, but altitude matters more
Predicted close approaches (SOCRATES, same-constellation pairs and formation-flyers removed) per object, for the 29,102 tracked objects in LEO:
| Type | Objects | Predicted close approaches per object this week | Share with at least one | Median altitude |
|---|---|---|---|---|
| payload (satellite) | 17,883 | 12.6 | 91% | 483 km |
| rocket body | 1,020 | 8.5 | 70% | 852 km |
| debris | 10,148 | 3.0 | 62% | 852 km |

Within the same altitude (this removes most of the confound), by radar cross-section (SATCAT RCS, a size proxy; known for only 37% of LEO objects):
| Altitude band | tiny (<0.01 m2) | 0.01 to 0.1 | 0.1 to 1 | 1 to 10 | big (>10 m2) |
|---|---|---|---|---|---|
| 450 to 600 km (Starlink shells), events per object | 31 | 32 | 25 | **61** | 38 (n=9) |
| 750 to 850 km (debris shells), events per object | 1.3 | 1.6 | 4.9 | 4.7 | 1.5 (n=30) |

What it supports, with care:
- **Altitude dominates.** An object at 450 to 600 km has roughly 20 to 40 times the predicted close approaches of a same-size object at 750 to 850 km. Across all objects, size alone correlates only weakly with close approaches (rank correlation 0.06).
- **Within a shell, bigger objects meet more traffic:** about 2 to 3 times more for objects of 1 to 10 m2 than for small ones, in both bands. The very largest bins have too few objects to trust.
- **Payloads meet more than debris** mainly because they sit in the busy low shells and because SOCRATES only reports pairs that include an active satellite.

## Limits (all of these matter)
- SOCRATES covers one week and only pairs with at least one active satellite, within about 5 km. It counts predicted close approaches, not collisions, and says nothing about untracked debris.
- Altitudes use each pair's average altitude. RCS is missing for 63% of objects, and sparse bins are noisy (tiny payloads: n=2, ignore).
- This is correlation in one snapshot, not proof that size causes close approaches.

## A feature this suggests
Let the user pick what they are launching (cubesat, small satellite, medium, large, station-size, plus a count). Show two things side by side: the model's collisions-per-year (scales with size, said to be a first-order estimate) and the **observed** exposure of existing objects of that size class in the chosen shell ("objects of 1 to 10 m2 at 450 to 600 km had about 61 predicted close approaches this week on average, against about 25 for 0.1 to 1 m2"). The observed number is new data the model does not have. It would be one new Chalk function (for example `similar_objects_exposure(altitude_km, rcs_m2)`) built from `data/raw/celestrak/satcat.csv` and SOCRATES, plus a tool-calling test case.

---

# Part 2: different KINDS of satellite (station, constellation, imaging, weather, cubesat, military)

Same snapshot. Kinds come from CelesTrak's own group files (`data/raw/celestrak/<group>.json`), the groups our pipeline already downloads. LEO only (200 to 2,000 km). "Events" = predicted SOCRATES close approaches this week (same-constellation pairs and formation-flyers removed), per object.

| Kind (CelesTrak group) | Objects | Typical altitude (10th to 90th pct) | Typical inclination | Events per object | Objects in its shell | Debris share of shell |
|---|---|---|---|---|---|---|
| Starlink (communications constellation) | 11,124 | 466 km (455 to 483) | 53.2 | 8.4 | 10,371 | 1% |
| Kuiper (constellation) | 391 | 630 km | 51.9 | 10.7 | 1,168 | 33% |
| OneWeb (constellation) | 651 | 1,202 km (1,182 to 1,218) | 87.9 | 3.6 | 478 | 26% |
| Qianfan (constellation) | 256 | 1,068 km (896 to 1,068) | 89.0 | 7.9 | 581 | 47% |
| Hulianwang (constellation) | 226 | 1,150 km | 50.0 | 3.5 | 445 | 54% |
| Earth imaging (Planet) | 123 | 470 km (414 to 503) | 97.4 | **53.8** | 10,371 | 1% |
| Weather | 50 | 483 km (378 to 828) | 97.5 | **69.8** | 10,371 | 1% |
| Cubesat | 83 | 556 km (438 to 680) | 97.7 | **42.4** | 1,309 | 17% |
| Science | 37 | 562 km (468 to 786) | 97.5 | **40.4** | 1,309 | 17% |
| Military | 45 | 945 km (942 to 952) | 81.5 | 15.4 | 936 | 74% |
| "Stations" group (see caveat) | 11 | 348 km (302 to 420) | 51.6 | 4.6 | 265 | 2% |
| All LEO objects | 29,102 | n/a | n/a | 9.2 | n/a | n/a |

The ISS alone (NORAD 25544): 419.5 km, 51.63 degrees, 3 predicted close approaches this week.

## What the data supports
- **Kinds sit in very different orbits.** Space stations (ISS, Tiangong) are low, near 420 km at 51.6 degrees. Big communications constellations fly mid-inclination (50 to 53 degrees) from 450 km up to about 1,200 km. Imaging, weather, cubesat and science satellites cluster at about 97 to 98 degrees (sun-synchronous), mostly 450 to 700 km. Military objects in this group sit in one debris-heavy shell near 945 km.
- **The sun-synchronous kinds see about 4 to 8 times the predicted close approaches** per object (40 to 70) of the mid-inclination constellations (3.5 to 11). A likely reason is geometry, not the satellite kind: a near-polar orbit at 450 to 600 km crosses the planes of every inclined constellation. That is a hypothesis; we did not test it.
- **Neighborhood size differs a lot:** 10,371 objects in the Starlink-weather-imaging shell, against 265 near the ISS group's altitude and 445 to 581 at OneWeb, Qianfan and Hulianwang altitudes. The high constellation shells have far more debris (26 to 54%) than the low ones (1%).

## Caveats
- The `stations` group is not pure: besides the ISS and Tiangong it holds visiting vehicles and small satellites deployed from them, so use the ISS row for "space station." With 11 objects, it is an example, not a statistic.
- SOCRATES only reports pairs that include an active satellite, and we removed same-constellation pairs. That deflates constellation members' counts (their own neighbors) while other kinds' counts include those encounters. So kind-to-kind comparisons are biased against showing constellations as risky.
- One week, predicted close approaches (not collisions), tracked objects only. Kind labels are CelesTrak's, not ours.

## Not in the current model
`pipeline/scoring.py` knows only altitude, size and count; kind and inclination do not enter the score. A "what kind of object are you launching?" picker could use these rows as presets (typical altitude and inclination) and show the observed exposure of that kind. That would be new information, available now.
