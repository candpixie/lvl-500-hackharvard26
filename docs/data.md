# Data inventory (Fri Oct 16, late)

Checked live. Everything below is free, and none of it needs a key unless noted.

## What's in orbit right now (CelesTrak SATCAT, `data/out/leo_shells.json`)
- **35,044 tracked objects still in Earth orbit**: 20,149 payloads, 12,543 debris pieces, 2,297 rocket bodies.
- **29,211 of them in low Earth orbit (under 2,000 km).**
- **11,154 are Starlink.**
- The catalog lists every tracked debris piece with its altitude range and inclination, so
  crowding by shell can be measured without a Space-Track account.

## Two shells tell the story
| Shell | Objects | Mostly |
|---|---|---|
| 450 to 500 km | 10,362 | Working satellites (Starlink) |
| 750 to 850 km | 3,263 | **Debris**, mostly from old breakups |

- Low shells are crowded with working satellites, but air drag cleans them out within years.
- The debris sits higher (750 to 850 km), where drag is too weak to clear it for a very long time.
  That's the sustainability point: junk lives where nature can't clean it up.
- Verify decay-time figures from a published source before any slide.

## Other sources
| Data | Where | Use |
|---|---|---|
| Live orbits of active satellites (16,754) | CelesTrak GP `GROUP=active` | Moving dots on the globe |
| Orbits of famous breakup debris (about 2,700) | CelesTrak GP debris groups (Fengyun-1C, Cosmos 2251, Iridium 33) | Moving debris on the globe |
| Orbits of **all** debris | Space-Track.org (free account) | Full moving debris field. Sign up tonight if we want it |
| Predicted close approaches | CelesTrak SOCRATES (daily) | Known answers to check our "crowding" score against |

## Gotchas
- CelesTrak throttles repeated group downloads (same group, about every 2 hours). Download once, cache in `data/raw/`.
- Catalog altitude is (apogee + perigee) / 2, a shell average. Fine for crowding, not for exact positions.
- Say "crowding" or "close approaches", never "collision probability". Real probability needs position
  uncertainty data we don't have.
- 17k to 30k moving dots must be drawn on the GPU (points), with positions precomputed or in a worker.

## Hook to test with the team
SpaceX filed (Jan 30 2026) for up to **1 million** orbital data center satellites. Low Earth orbit holds
about **29,000** tracked objects today. Where would a million more fit, and what would that shell look like?

## Update: everything free is downloaded (`pipeline/fetch_orbits.py`, Fri late)
Raw files land in `data/raw/celestrak/` (not committed). Run the script once per person.

**Coverage: 20,039 objects with orbits out of 35,044 tracked in orbit.**
| Type | Have orbits | In orbit | Missing |
|---|---|---|---|
| Payloads (satellites) | 16,739 | 20,149 | about 3,400 (mostly dead satellites) |
| Debris | 2,680 | 12,543 | about 9,900 |
| Rocket bodies | 12 | 2,297 | **almost all** |

- Free CelesTrak feeds cover working satellites and the famous breakups only.
- **Rocket bodies are the biggest objects in orbit and we have almost none of them.** For a real
  "what's around my spot" view, we need **Space-Track** (free account, `gp` class has all ~30k).
  Read its user agreement before putting any of its data in a public repo.
- The `starlink` group returned 403 (throttled). Starlink is already inside `active`, label by name.

**SOCRATES: 195,841 predicted close approaches** for the next 7 days (`socrates-minrange.csv`):
both objects, time of closest approach, miss distance (km), relative speed (km/s), max probability.
- This is the real-world answer key for any "crowding" score we make.
- Filter out pairs from the same constellation (Starlink vs Starlink pairs show probability 1.0,
  likely formation flying or a modeling artifact). Check the SOCRATES format page before trusting MAX_PROB.

## Update: frontend-ready files (`pipeline/build_objects.py`)
- `data/out/objects.json`: 20,038 objects (16,753 satellites, 2,679 debris, 12 rocket bodies,
  594 unidentified), each with orbit elements plus catalog info. Not committed (14 MB).
- `data/out/close_approaches.json`: 500 closest predicted approaches. Removed same-constellation
  pairs and objects with almost no relative speed (they fly together, like a spacecraft and its own
  launch debris, not near misses).
- Closest real one this week: NuSat-47 vs Fengyun-1C debris, 12 m apart, 14.5 km/s, Oct 22.
