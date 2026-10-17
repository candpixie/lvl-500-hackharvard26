# Orbit Payback: project brief (for Cursor)

HackHarvard 2026. Read this first, then `README.md` and `docs/data.md`.
Devpost is due **Sun 8:00 AM**. Gates: **Sat 2 PM** everything connected end to end (even if ugly),
**Sat 6 PM** feature freeze and backup video.

## 1. What we're building

**Space is the next environment we're about to pollute.** In January 2026, SpaceX filed for up to
**1,000,000** orbital data center satellites. About 29,000 tracked objects are in low Earth orbit today.

The app answers: *if we put something in orbit, where does it do the least harm?*

1. A **3D globe** of every tracked object (~20k with orbits), colored by type: satellite, debris, rocket body.
2. **Place your satellite:** pick altitude, inclination, size and count (1 to 1,000,000). See how crowded
   that shell is, the expected collisions per year, and how long a dead satellite would stay up.
3. **Shell ranking:** the safest shells from 500 to 2,000 km, each with a one-line reason.
4. **A Grok agent you can talk to** (voice): "Where should I put 1,000 satellites?" It answers with real
   numbers from our data, out loud, and the globe flies to the orbit it recommends.

### The story the data tells (the demo)
- Working satellites crowd the low shells (450 to 500 km: about 10,000 objects, mostly Starlink).
  Air drag clears dead ones there within years.
- Debris piles up higher (peak at 800 to 850 km: about 1,400 pieces from the 2007 Chinese ASAT test and the
  2009 Iridium-Cosmos collision). Drag can't clear it for centuries. **Junk lives where nature can't clean it up.**
- So low shells win: a failure at 500 km clears itself in about a decade. That matches SpaceX's own plan to
  start below 600 km.
- Click **Show debris only** while the bright shell is up, so the amber debris is obvious, then turn it off.

## 2. Prizes and what each one requires

| Prize | Requirement | How we meet it |
|---|---|---|
| **SpaceX AI "Make It Legendary"** (main) | Real space data. **Built with Cursor** (more use = better odds). **Must use the Grok Imagine or Voice API.** Bonus: Grok Bot for planning. | CelesTrak data. All app code written in Cursor. Grok agent answers out loud with the Voice API. |
| **Sustainability track** | Sustainability impact | Space debris is pollution that lasts for centuries. |
| **Chalk "Data-Driven Agent"** (only if the eval is real) | Judged on impact, data and **evals** | The Grok agent is the agent. Eval: does it steer away from shells where SOCRATES shows real near misses? Report a number. |

## 3. Framing rules (apply to all UI copy and agent answers)
- **Not** claiming space data centers are greener than Earth ones (research says orbital compute has *higher*
  carbon cost). Our angle: *if* we build in orbit, where does it do the least harm?
- Never frame SpaceX as the villain. Neutral: "where to build safely."
- Every risk number is labeled **"tracked objects only, lower bound."**
- Say "crowding" or "close approach". Never say "collision probability" unless it's SOCRATES's own number.
  "Expected collisions per year (first-order model)" is OK.
- Every number on screen has a source (tooltip).
- Any Grok Imagine image or video is labeled as illustration. Data is drawn from data.

## 4. Team roles

| # | Role | Owns |
|---|---|---|
| 1 | Globe lead | `web/` skeleton: globe, ~20k points as one GPU point cloud, SGP4 in a Web Worker. Sets the look. Reviews UI PRs. |
| 2 | Place-your-satellite UI | Altitude / inclination / size controls, highlighted shell, results panel, click a dot for its story. |
| 3 | **Grok agent + voice (David)** | `api/` server, the data tools, Grok answering with real numbers, Voice API, sending `focusOrbit` events. |
| 4 | Data, eval, story | Space-Track refresh, Chalk eval vs SOCRATES, "near miss replay", fact-checking every slide number. |

**Shared contract (everyone codes against this):**
- One web app in `web/` (Vite + React + globe.gl or three.js; the globe lead picks).
- Everyone reads the same files in `data/out/`.
- Two shared frontend events:
  - `focusOrbit({ altitude_km, inclination_deg })`: the globe flies there and highlights that shell.
  - `selectObject(norad)`: the globe highlights that object and the panel shows its info.
- One owner per folder. One branch per person, merge into `main` every ~2 hours.

## 5. Repo layout (today)

```
pipeline/            Python, offline. Builds everything in data/out/.
  fetch_orbits.py    downloads CelesTrak data into data/raw/celestrak/ (not committed; throttled ~2 h per group)
  build_objects.py   writes data/out/objects.json (14 MB, gitignored) + close_approaches.json
  leo_shells.py      older shell counts (superseded by orbit_data.py)
  orbit_data.py      crowding by shell and by altitude x inclination, collision rate, decay table
  scoring.py         place() and rank(): score 0 to 100 and the shell ranking
  shadow.py          leftover from an earlier idea, ignore
data/out/            built JSON the app reads (see section 6)
docs/                data.md (data inventory and gotchas), this file
archive/             earlier project direction, ignore
api/                 NOT YET: FastAPI server + Grok agent (role 3)
web/                 NOT YET: frontend (roles 1 and 2)
```

Setup: install [uv](https://docs.astral.sh/uv/), then from the repo root:

```sh
uv run python pipeline/fetch_orbits.py
uv run python pipeline/build_objects.py
uv run python pipeline/orbit_data.py
uv run python pipeline/scoring.py       # prints the ranking as a check
```

## 6. Data files (`data/out/`)

| File | Contents |
|---|---|
| `objects.json` | `{source, count, objects: [...]}`. Each object: `norad, name, type` (satellite / debris / rocket body / unknown), `owner, launch_date, radar_size_m2, apogee_km, perigee_km, constellation, groups, source_group, omm`. `omm` feeds straight into satellite.js **v6+** `json2satrec()`. Gitignored; build it locally. |
| `shells.json` | `{source, shells: [...]}`, one row per 50 km shell from 300 to 2,000 km: `alt_lo, alt_hi, PAY, R/B, DEB, UNK, total, density_per_km3`. Counts are time-weighted (fractional). |
| `crowding_grid.json` | `{source, alt_step_km: 50, inc_step_deg: 10, types, rows: [...]}`. Rows: `alt_lo, alt_hi, inc_lo, inc_hi, PAY, R/B, DEB, UNK, total`. For the heatmap. |
| `decay_table.json` | `{source, rows: [{alt_km, years}]}`. **Approximate** years a dead satellite stays up. Verify before a slide. |
| `close_approaches.json` | `{source, rows: [...]}`, the 500 closest predicted approaches in the next 7 days (CelesTrak SOCRATES): `norad_1, name_1, norad_2, name_2, time_utc, miss_distance_km, relative_speed_km_s, max_probability`. |

Coverage gap: free CelesTrak orbits cover ~20k of 35k tracked objects (most debris and almost all rocket
bodies are missing). The crowding counts in `shells.json` use the full SATCAT catalog, so they are complete
for tracked objects. Space-Track would fill in the orbits (role 4).

## 7. The model (in `pipeline/orbit_data.py` and `pipeline/scoring.py`)

Simple on purpose, and we say so on screen.
- **Shell density** = objects in the shell / shell volume (objects per km³). Each object's time is spread evenly
  between its perigee and apogee.
- **Collisions per year (one object)** = density × v_rel × A × seconds per year, with v_rel = 10 km/s,
  A = π(r_obj + 0.5 m)², r_obj = half the longest dimension.
- **Constellation of N:** each satellite also sees the other N−1 added to its shell. For 1,000,000 satellites
  this self-crowding term dominates (and in reality they'd maneuver to avoid each other). Say that in the demo.
- **Dead-satellite lifetime:** log-interpolated from rough anchors (400 km ≈ 1 yr, 500 ≈ 8, 600 ≈ 25,
  800 ≈ 200, 1,000 ≈ 1,000 years). Depends on solar activity by ~10×.
- **Score 0 to 100 (higher = safer):** 80% long-term harm (collisions/yr × years the wreckage stays up),
  10% collisions/yr, 10% density. Each is log-scaled against the shells from 500 to 2,000 km. Weights live in
  `WEIGHTS` in `scoring.py`.
- Inclination does not change the score yet (density is per shell).

### Python functions to reuse (import from `pipeline/`)
```python
from orbit_data import shells, crowding_grid, collision_rate, dead_sat_lifetime_years
from scoring import place, rank

place(alt_km=550, inc_deg=53, dims_m=[4, 2, 1], count=1000)
# -> {alt_km, inc_deg, dims_m, count, shell, objects_before, objects_after,
#     collisions_per_year, collisions_per_year_one, close_passes: None, nearest: None,
#     dead_sat_lifetime_years, score, note}

rank(dims_m=[4, 2, 1], count=1000, top=10)
# -> [{alt_lo, alt_hi, score, collisions_per_year, dead_sat_lifetime_years, objects, reason}, ...]
```
These modules import each other by bare name, so code in `api/` must add `pipeline/` to `sys.path`
before importing. `shells()` reads the SATCAT CSV (~1 s); cache it once at startup.

Sanity numbers (4×2×1 m satellite): safest shells are 500, 550, 600 km. 1M satellites at 550 km scores
~78; at 900 km ~42. Debris peaks at 800 to 850 km. If those change a lot, something broke.

## 8. Role 3 spec: Grok agent + voice (`api/`)

### Server
FastAPI, run with `uv run uvicorn api.main:app --reload`. No network calls at request time except to xAI.
Keys in `.env` (gitignored): `XAI_API_KEY`. Never commit keys.

| Endpoint | Returns |
|---|---|
| `GET /shells` | `shells.json` rows |
| `POST /place {alt_km, inc_deg, dims_m, count}` | `place(...)` |
| `GET /rank?dims=4,2,1&count=1000` | `rank(...)`, top 10 |
| `GET /close_approaches?alt_km=800&limit=10` | SOCRATES rows near that altitude (needs a small lookup: join `norad_1/2` to `objects.json` for altitude) |
| `POST /ask {question}` | `{answer, focus, tool_calls}`: Grok's answer, an optional `focusOrbit` payload, and which tools it called (shown in the UI as "sources") |
| `POST /speak {text}` (or streamed with `/ask`) | Audio from the Grok Voice API |

### The agent
- Grok with tool calling (the xAI API is OpenAI-compatible; check docs.x.ai for the current model name, the
  tool-calling format and the **Voice API**).
- Tools = the data functions: `get_shell_crowding(alt_km)`, `place_satellites(alt_km, inc_deg, dims_m, count)`,
  `rank_shells(dims_m, count)`, `get_close_approaches(alt_km)`.
- System prompt: answer **only** from tool results, quote the numbers, say "tracked objects only, lower bound",
  follow the framing rules in section 3, keep answers short enough to speak (~3 sentences).
- After `place_satellites` or `rank_shells`, set `focus = {altitude_km, inclination_deg}` from the top result.
  The frontend calls `focusOrbit(focus)` so the globe flies there.

### Order of work
1. `api/main.py` serving `/shells`, `/place`, `/rank` from the Python functions. Test with curl.
2. `/ask` with Grok + tools, tested with typed questions (no globe needed).
3. Voice: Grok speaks the answer (**required** for the SpaceX AI prize, so get a basic version working early).
4. `focus` wired to the globe once roles 1 and 2 have `focusOrbit` working.
5. Stretch: `/close_approaches` tool, and help role 4 run the Chalk eval against `/ask`.

### Demo questions the agent must handle
- "Where should I put 1,000 four-meter satellites?"
- "What happens if SpaceX puts a million satellites at 900 km?"
- "Why is 800 km so bad?"
- "What's the closest near miss this week?"

## 9. Conventions
- Python 3.11+, run everything through `uv`. Units in names: `alt_km`, `dims_m`, `v_rel_kms`.
- Don't commit `data/raw/`, `objects.json`, `.env` or anything from Space-Track.
- Keep a log of Cursor and Grok Bot use (needed for the SpaceX AI prize).
- Sources to credit: CelesTrak (GP, SATCAT, SOCRATES), Space-Track.org, satellite.js.
