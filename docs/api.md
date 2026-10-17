# Deployed Chalk functions: reference

The team's API is `api/` (FastAPI, port 8000) with `/ask`, `/listen`, `/imagine`, `/speak` and `/health`, the Grok loop in `api/agent.py` and the Chalk client in `api/chalk.py`. The Chalk-hosted ask service is documented in `docs/chalk-ask-service.md`. This file documents the four functions deployed to Chalk, which `api/chalk.py` can call with `CHALK_REMOTE_FUNCTIONS=1`.

## Calling them from Python
```python
import json, chalkcompute
shell = chalkcompute.RemoteFunction.from_name("shell_crowding", call_timeout=5)
result = json.loads(shell.remote(550.0, None))      # returns the JSON TEXT of the envelope; json.loads it
```
- `from_name(...)` does NOT apply default arguments. Pass EVERY argument, positionally, in the order below.
- Needs the Chalk login on the calling machine (`chalk login`) or a client id and secret in the environment.
- Measured: about 200 ms on the first call, 30 to 50 ms after. Importing `chalk_tools.functions` deploys; never import it, call `core` locally instead.

| Function | Arguments (all required when called remotely) |
|---|---|
| `shell_crowding` | `altitude_km: float`, `inclination_deg: float or None` |
| `objects_near` | `altitude_km: float`, `inclination_deg: float`, `limit: int` |
| `close_approaches` | `min_altitude_km: float`, `max_altitude_km: float`, `limit: int` |
| `recommend_orbit` | `inclination_deg: float`, `min_altitude_km: float`, `max_altitude_km: float`, `top_n: int`, `inclination_band_deg: float` |

Every result is `{"ok": true, "data": {...}, "coverage": {...}, "caveats": [...], "snapshot_id": "..."}` or `{"ok": false, "error": {"type": "out_of_range|invalid_argument", "message": "..."}, "snapshot_id": "..."}`. Valid altitudes are 200 up to 2000 km, inclination 0 to 180.

## What each means (so Grok describes it correctly)
- `shell_crowding`: tracked objects by type in the 50 km shell holding that altitude (optionally near one inclination), plus objects per million km^3. Counts by average altitude.
- `objects_near`: tracked objects whose orbit passes through that altitude at a similar inclination, nearest first. Same altitude and plane, NOT a distance or collision estimate.
- `close_approaches`: SOCRATES predictions for one week whose two objects average inside the altitude band. `max_probability` is SOCRATES's own number; `probability_flag: "suspect"` means about 1.0 and unverifiable.
- `recommend_orbit`: the quietest shells for an inclination (expected objects in the shell at a random moment). Quiet means few tracked objects, not safe, and many quiet high shells are mostly debris (`debris_share`). It does not use SOCRATES. It is separate from the team's `rank()` in `pipeline/scoring.py`.

## Data snapshot caveat
The deployed functions answer from snapshot `d29cf5404f55` (CelesTrak SATCAT and SOCRATES fetched Sat Oct 17, window Oct 16 to 23). The committed `data/out/` files and the demo script use Friday night's snapshot (for example the NuSat-47 vs Fengyun-1C 12 m approach, which is NOT in the newer SOCRATES file). The two paths can disagree on counts and on the closest near miss until the team freezes one snapshot. Results and eval numbers for my functions are in `docs/eval_results.md`.
