# Chalk pair: how to plug into this repo

You own **data + reasoning + the eval**. Grok is only the front door (speech in, speech out, Imagine pictures). Do not rebuild the globe or the collision model.

If Chalk is down, Grok already falls back to the same Python functions you should wrap. Your job is to become the primary path and prove it with an eval.

## What already works (do not redo)

| Piece | Where | You do |
|---|---|---|
| SATCAT crowding, decay, collision rate | `pipeline/orbit_data.py` | Wrap as Chalk resolvers |
| `place()` / `rank()` scores | `pipeline/scoring.py` | Wrap as Chalk resolvers |
| SOCRATES near-misses | `data/out/close_approaches.json` | Read / join, do not scrape again |
| Shell counts | `data/out/shells.json` | Optional cache; `shells()` is the source of truth |
| FastAPI + Grok tool `ask_chalk` | `api/chalk.py`, `api/agent.py` | Hit this contract |
| Globe + `focusOrbit` | `web/` | Nothing. We consume your `focus` |

Built data lives in `data/out/`. `objects.json` is gitignored (14 MB); run `uv run python pipeline/build_objects.py` if you need it. SATCAT is `data/raw/celestrak/satcat.csv` (also gitignored; `uv run python pipeline/fetch_orbits.py` once).

## Repo path for your agent

```
user voice/text
    → Grok STT (optional)
    → POST /ask on this repo (port 8000)
    → Grok is forced to call tool ask_chalk
    → POST $CHALK_ASK_URL   ← you
    → you run place / rank / shells / SOCRATES
    → you return {answer, focus, tool_calls}
    → Grok speaks it + Imagine (labeled illustration)
    → globe flies to focus.altitude_km
```

Grok must not invent numbers. If you return an `error`, it uses local `pipeline/` instead.

## 1. Reuse the model (add `pipeline/` to `sys.path`)

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("pipeline").resolve()))  # repo root / pipeline

from orbit_data import shells, collision_rate, dead_sat_lifetime_years
from scoring import place, rank
```

Cache `shells()` once at startup (~1 s, reads SATCAT).

```python
place(alt_km=550, inc_deg=53, dims_m=[4, 2, 1], count=1000)
# score, collisions_per_year, dead_sat_lifetime_years, objects_before, note

rank(dims_m=[4, 2, 1], count=1000, top=10)
# safest shells first; each has reason, score, lifetime
```

Sanity: 4×2×1 m sat, safest shells **500 / 550 / 600 km**. 1M at 550 ≈ score **78**; at 900 ≈ **42**. Debris peak **800–850 km**. If those move a lot, you are not calling our functions.

Close approaches: load `data/out/close_approaches.json`. Closest this week is NuSat-47 vs Fengyun-1C debris, **12 m**, Oct 22. Join NORAD ids to `objects.json` for altitude if you need it.

## 2. Expose one HTTP endpoint

`POST $CHALK_ASK_URL`  (example: `https://<your-chalk>/ask` or `http://127.0.0.1:8001/ask`)

Request:

```json
{ "question": "Where should I put 1,000 four-meter satellites?" }
```

Optional headers we already send: `Authorization: Bearer $CHALK_TOKEN`, `x-chalk-env-id: $CHALK_ENV_ID`.

**200 response (this shape is required):**

```json
{
  "answer": "Three short spoken sentences. Quote your resolver numbers. Say tracked objects only, lower bound once.",
  "focus": { "altitude_km": 525, "inclination_deg": 53 },
  "tool_calls": [
    {
      "name": "rank_shells",
      "arguments": { "count": 1000, "dims_m": [4, 2, 1] },
      "result": { "...": "the rank() rows" }
    }
  ],
  "note": "tracked objects only, lower bound"
}
```

- `focus` is required whenever you recommend a shell. The globe calls `focusOrbit(focus)`.
- `tool_calls` is what the UI shows as sources. Use names: `rank_shells`, `place_satellites`, `get_shell_crowding`, `get_close_approaches`.
- On failure: HTTP 4xx/5xx or `{"error": "reason"}`. That triggers Grok's local fallback.

Which tool for which question:

| User says | Call | `focus.altitude_km` |
|---|---|---|
| Where should I put N sats? | `rank(...)`, take the top row | mid of top shell (`alt_lo + 25`) |
| What if N sats at X km? | `place(X, ...)` | `X` |
| Why is 800 km bad? | shell row ~800 + close approaches | `825` |
| Closest near miss this week? | first row of close approaches | that pair's mean altitude |

## 3. Copy rules (UI + judges will see this)

- Say **crowding** or **close approach**. Never “collision probability” unless you are quoting SOCRATES `max_probability`.
- “Expected collisions per year (first-order model)” is the correct rate label.
- Every risk number: **tracked objects only, lower bound.**
- Do not claim orbital data centers are greener than Earth ones.
- Do not frame SpaceX as the villain.
- Keep `answer` to ~3 spoken sentences.

## 4. Hook it to David’s API

On the machine running `uv run uvicorn api.main:app --reload --port 8000`, add to the gitignored `.env` (never `VITE_*`):

```
CHALK_ASK_URL=
CHALK_TOKEN=
CHALK_ENV_ID=spcwce09a241
```

`CHALK_ASK_URL` stays empty until you send the POST URL. `spcwce09a241` is the environment id, not a secret. The client times out at 5 seconds. The bearer is attached only for `https://`, and for `http://` on localhost, `127.0.0.1`, or `::1`.

Restart uvicorn. Check:

```sh
curl -s http://127.0.0.1:8000/health
# "chalk": true, "reasoner": "chalk"   once the URL answers
```

Health GETs `CHALK_ASK_URL` and does not send a question. 405 still counts as up. `"chalk": false` with no `chalk_error` means the URL is empty. `chalk_error` of `unreachable`, `auth`, `not_found`, or `http_5xx` means the probe failed. Response bodies are not returned.

Then:

```sh
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Where should I put 1,000 four-meter satellites?"}'
```

You want `"reasoner":"chalk"` and `focus.altitude_km` near 525. The globe at `http://127.0.0.1:5173` should fly there.

If health still says `"chalk": false` and there is no `chalk_error`, `CHALK_ASK_URL` is empty or the API was not restarted.

Your function envelope `{ok, data, coverage, caveats, snapshot_id}` is not the `/ask` body. HTTP `/ask` must still return `{answer, focus, tool_calls}`. The three deployed functions can also be called directly: set `CHALK_REMOTE_FUNCTIONS=1` and install `chalkcompute`. Grok then gets `shell_crowding`, `objects_near`, and `close_approaches` via `RemoteFunction.from_name`. `recommend_orbit` is not wired. `rank_shells` and `place_satellites` stay the local placement tools.

For the eval task, import `run_agent(question, history, context)` from `agent`. It calls the same loop as `/ask` and does not store history. The return is the `/ask` object plus `ui_events`.

## 5. Eval (this is the Chalk prize)

Chalk judges **impact, data, evals**. Run Agent Evals (or a script) on the four demo questions plus a few random counts/altitudes.

**Scorer:** when the user asks where to put something, `focus.altitude_km` is **not** in 750–850 km, and `dead_sat_lifetime_years` is under ~25. Report a number, e.g. **12/12 recs stay out of the 800 km junk band.**

Demo questions your eval must cover:

1. Where should I put 1,000 four-meter satellites?
2. What happens if SpaceX puts a million satellites at 900 km?
3. Why is 800 km so bad?
4. What's the closest near miss this week?

Same functions in eval and in the live `/ask` path. Do not score a different model than the one Grok calls.

## 6. Branch / files you can add

Put Chalk feature code in a new folder, e.g. `chalk/` on your own branch. Do not rewrite `web/` or `api/agent.py` unless you are pairing with David. The only shared surface is `POST $CHALK_ASK_URL` plus `.env`.

Questions: `api/chalk.py` (the client) and this file. Data gotchas: `docs/data.md`. Product rules: `docs/project-brief.md`.
