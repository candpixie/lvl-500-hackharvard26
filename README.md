# orbit-payback (working name, rename TBD)

HackHarvard 2026. **Before you launch, see how crowded your orbit is and what's flying near it.**
Pick what you want to put in space and where (altitude, inclination). We place it among every tracked
satellite and piece of debris, show what's close and how risky the neighborhood is, and suggest
better spots.

## Why now
- SpaceX filed (Jan 30 2026) for up to **1 million** orbital data center satellites.
  Low Earth orbit holds about **29,000** tracked objects today. Where would a million more go?
- Working satellites crowd the low shells (450 to 500 km: about 10,000 objects, mostly Starlink),
  where air drag clears dead ones within years.
- Debris piles up higher (750 to 850 km: about 3,300 objects, mostly debris), where drag can't
  clear it for a very long time. Junk lives where nature can't clean it up.
- Real example from this week's predictions: working satellite NuSat-47 is predicted to pass
  **12 meters** from a piece of Fengyun-1C debris (from a 2007 missile test) at 14.5 km/s on Oct 22.
  (SOCRATES prediction, verify before using on a slide.)

## MVP (in this order)
1. Plot every object we have on a 3D globe, colored by type (satellite, debris, rocket body).
2. User places their object (altitude + inclination, maybe size).
3. Show what's near it and how crowded that shell is.
4. Then make it cool: zoom, click an object for its story, suggest better spots.

## Prizes we're aiming at
- **SpaceX AI "Make It Legendary":** real space data (yes), built in **Cursor** (log it), plus Grok
  Imagine or Voice (still to decide how).
- **Sustainability track:** space sustainability, debris that stays up for a very long time.
- **Chalk "Data-Driven Agent":** judged on impact, data and evals. Open question: what's the
  agent? SOCRATES close approaches can be the eval answer key.

## Data (`docs/data.md` has the full inventory)
| What | Source | In our build |
|---|---|---|
| Orbits of 16,754 active satellites | CelesTrak GP `active` | yes |
| Orbits of about 2,700 debris pieces from big breakups | CelesTrak GP debris groups | yes |
| 594 tracked but unidentified objects | CelesTrak GP `analyst` | yes |
| Every tracked object: type, owner, launch date, radar size, altitude | CelesTrak SATCAT | yes |
| 195,841 predicted close approaches, next 7 days | CelesTrak SOCRATES | top 500 in `close_approaches.json` |
| Orbits of **all** debris and rocket bodies (about 30,000) | Space-Track.org, free account | **not yet** |

Coverage today: orbits for 20,038 of 35,044 tracked objects. We're missing most debris and almost
all rocket bodies. Space-Track fills that in. Read its user agreement first, and never commit its data.

## Get the data
Needs [uv](https://docs.astral.sh/uv/). From the repo root:

```sh
uv run python pipeline/fetch_orbits.py    # downloads into data/raw/celestrak/ (not committed)
uv run python pipeline/build_objects.py   # writes data/out/objects.json + close_approaches.json
uv run python pipeline/leo_shells.py      # (optional) crowding by 50 km shell
```

CelesTrak blocks repeat downloads of the same group for about 2 hours. The fetch script keeps
anything newer than that, so it's safe to rerun.

### `data/out/objects.json`
One entry per object: `norad`, `name`, `type`, `owner`, `launch_date`, `radar_size_m2`,
`apogee_km`, `perigee_km`, `constellation`, `groups`, and `omm` (the orbit elements).
It's 14 MB and regenerated, so it's in `.gitignore`.

### `data/out/close_approaches.json`
The 500 closest predicted approaches, with same-constellation pairs and objects flying together
removed: both objects, time, miss distance (km), relative speed (km/s), max probability.

## Positions (how the globe moves)
- Nobody publishes positions directly. We get orbit elements and compute positions with **SGP4**.
- In the browser, use `satellite.js` **6.0 or later**. `json2satrec(obj.omm)` reads our OMM directly.
  Version 5 doesn't have it.
- Checked Fri night: all 16,754 active satellites propagate in about 100 ms, and our ISS position
  matched a live tracker within about 2 km.
- To avoid lag: run SGP4 in a **Web Worker** about once a second, draw everything as **one GPU point
  cloud**, and let the GPU animate between updates. Don't precompute timelines (hundreds of MB).

## Rules
- Say "crowding" or "close approach", never "collision probability" unless it's SOCRATES's own number.
- Every number on screen has a source.
- Any Grok image or video is illustration and labeled that way. Data is drawn from data.
- The web app is built in Cursor (SpaceX AI requirement). Keep a log of Cursor and Grok Bot use.
- Don't commit `data/raw/`, `objects.json` or anything from Space-Track.

## Working together
- One branch per person, PRs into `main`.
- Rename the repo once we have a name.

## Layout
- `pipeline/` Python, offline. Fetches and builds the JSON the web app reads.
- `data/out/` built data (small files committed, big ones ignored).
- `docs/data.md` data inventory and gotchas.
- `web/` frontend (Cursor).
- `archive/carbon-payback/` our first direction, kept for reference.

## Sources
- CelesTrak GP data, SATCAT and SOCRATES: https://celestrak.org
- Space-Track.org (18th Space Defense Squadron): https://www.space-track.org
- satellite.js (SGP4 in JavaScript), skyfield (Python)

## License
MIT. See LICENSE.
