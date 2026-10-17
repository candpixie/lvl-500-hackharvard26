# Chalk contract (HackHarvard)

Start here if you are on the Chalk pair: **[docs/chalk-teammates.md](chalk-teammates.md)** (repo map, imports, wiring, eval). This page is the HTTP shape only.

Grok is the front door (STT, TTS, Imagine). **Chalk does data + reasoning.**
Local `pipeline/` tools run only if this endpoint errors or `CHALK_ASK_URL` is unset.

## Endpoint

`POST $CHALK_ASK_URL`

Optional: `Authorization: Bearer $CHALK_TOKEN`, `x-chalk-env-id: $CHALK_ENV_ID`.

### Request

```json
{ "question": "Where should I put 1,000 four-meter satellites?" }
```

### Response `200`

```json
{
  "answer": "Three short spoken sentences. Quote your resolver numbers. Say tracked objects only, lower bound once.",
  "focus": { "altitude_km": 525, "inclination_deg": 53 },
  "tool_calls": [
    {
      "name": "rank_shells",
      "arguments": { "count": 1000, "dims_m": [4, 2, 1] },
      "result": {}
    }
  ],
  "note": "tracked objects only, lower bound"
}
```

`focus` is required whenever you recommend a shell. The globe calls `focusOrbit(focus)`.

On failure return **4xx/5xx** or `{"error": "reason"}`. Grok then uses local `place` / `rank` / SOCRATES.

## Resolvers to wrap (do not rewrite)

Import from `pipeline/` (add that folder to `sys.path`):

```python
from orbit_data import shells, crowding_grid, collision_rate, dead_sat_lifetime_years
from scoring import place, rank
```

| Tool | Function | Use |
|---|---|---|
| shell crowding | `shells()` / row for `alt_km` | "why is 800 km bad" |
| place | `place(alt_km, inc_deg, dims_m, count)` | specific altitude |
| rank | `rank(dims_m, count, top=10)` | "where should I put N" |
| close approaches | `data/out/close_approaches.json` | "closest near miss" |

Framing: crowding / close approach, never "collision probability" unless quoting SOCRATES `max_probability`. Neutral on SpaceX. Not claiming orbital compute is greener.

## Eval (the Chalk prize)

Same four demo questions plus a few random counts/altitudes.

**Scorer:** recommended `focus.altitude_km` is **not** in 750–850 km, and `dead_sat_lifetime_years` from `place`/`rank` is under 25 when the user asked where to put something. Report `N/M` cases that steer out of the junk band.

Demo questions:

1. Where should I put 1,000 four-meter satellites?
2. What happens if SpaceX puts a million satellites at 900 km?
3. Why is 800 km so bad?
4. What's the closest near miss this week?

## Local wiring

The client waits **5 seconds** on `POST $CHALK_ASK_URL`, then uses local `place` / `rank` / SOCRATES. The bearer token is sent only to `https://` URLs, or to `http://` on localhost, `127.0.0.1`, or `::1`.

No ask URL has been provided yet. Leave `CHALK_ASK_URL` empty until Person A sends one. Their Chalk environment id is `spcwce09a241` (an id, not a key). Put these in the gitignored `.env` on the API machine. Do not put them in `VITE_*`.

```
CHALK_ASK_URL=
CHALK_TOKEN=
CHALK_ENV_ID=spcwce09a241
```

`GET http://127.0.0.1:8000/health` probes that URL with GET (it does not send a question). Any response under 500 except 401, 403, and 404 counts as up, including 405 from a POST-only route. `"chalk": true` means the probe succeeded. If the URL is empty, the probe is skipped and `"chalk"` stays false.

`/ask` is unchanged: `{question}` in, `{answer, focus, tool_calls, reasoner}` out. When `CHALK_ASK_URL` is set, Grok still calls `ask_chalk` first even if the last health probe failed.

Their deployed functions return `{ok, data, coverage, caveats, snapshot_id}`, not the ask contract. That shape is only for the optional direct tools below. `recommend_orbit` is not deployed; `rank_shells` and `place_satellites` stay local.

Optional, off unless set to `1`: `CHALK_REMOTE_FUNCTIONS`. Grok can then call `shell_crowding`, `objects_near`, and `close_approaches` with `RemoteFunction.from_name` (5s timeout). Requires `chalkcompute` installed and a Chalk login on the API machine. Do not import `chalk_tools.functions`; importing it deploys.

Eval import, same loop as `/ask`, no session store: `from agent import run_agent` then `run_agent(question, history, context)`. It adds `ui_events` with `focusOrbit` when there is a focus.
