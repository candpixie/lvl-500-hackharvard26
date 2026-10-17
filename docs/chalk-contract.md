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

```
# .env on the API box
CHALK_ASK_URL=https://your-chalk-host/ask
CHALK_TOKEN=
```

Then `GET http://127.0.0.1:8000/health` should show `"chalk": true`. `/ask` forces Grok to call `ask_chalk` first.
