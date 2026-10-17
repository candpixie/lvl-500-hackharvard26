# Chalk ask service (the `CHALK_ASK_URL` endpoint)

Built by Person A to satisfy `docs/chalk-contract.md`. Grok's `ask_chalk` tool posts the user's question here; this service runs the team's own `pipeline/scoring.py` (`rank`, `place`) and shell data, plus the SOCRATES near misses, and returns `{answer, focus, tool_calls, note}`. No LLM runs inside it, so answers are repeatable.

## Live
- URL: `https://spcwce09a241-orbit-ask.mdwje5.svls.customers.gcp.chalk.ai/ask` (Chalk environment `spcwce09a241`, scaling group `orbit-ask`)
- Auth: it REQUIRES a Chalk access token (`authenticated=True`). No token returns 401.
- Latency: about 270 to 350 ms.

## Put it in the API machine's `.env` (gitignored, never `VITE_*`)
```
CHALK_ASK_URL=https://spcwce09a241-orbit-ask.mdwje5.svls.customers.gcp.chalk.ai/ask
CHALK_TOKEN=<output of: chalk token get --expires-in 24h>
CHALK_ENV_ID=spcwce09a241
```
Then restart uvicorn and check `curl -s http://127.0.0.1:8000/health` shows `"chalk": true`. Tokens expire (24h here). A token acts as the Chalk user who created it, so each teammate should create their own after being invited to the Chalk team (Settings, Users and roles), not share one.

## What it answers
Rules, no model: `where should I put N ...` (rank), `what happens if N satellites at X km` (place), `why is X km so bad` (shell row, lifetime, nearest SOCRATES pair), `how crowded is X km`, `closest near miss` (optionally `around X km`). Sizes ("four-meter", "6 m"), counts ("1,000", "a million", "2.5 million") and mission phrases (polar, sun-synchronous, ISS, equatorial, "N degrees") are parsed from the question. Anything else returns HTTP 422 `{error}`, so Grok falls back to the local tools. Out-of-range altitudes (outside 300 to 2,000 km) also return 422.

## Data it uses (important)
- `data/out/shells.json` and `data/out/close_approaches.json` as committed (Friday night's snapshot), so numbers match the docs: best shells 500/550/600 km for 4x2x1 m, a million satellites scores 77.8 at 550 km and 42.4 at 900 km, closest near miss NuSat-47 vs Fengyun-1C at 12 m. The service reports their short hashes at `GET /health`.
- Near-miss altitudes are joined from a SATCAT catalog file (`data/out/tools/catalog.csv.gz`, built by `pipeline/build_tools_data.py` from today's SATCAT). Mean altitudes barely move between days.
- The deployed Chalk functions in `docs/api.md` (shell_crowding, objects_near, close_approaches, recommend_orbit) answer from a different, newer snapshot. Until the team freezes one snapshot, those two paths can disagree.

## Files and redeploying
`chalk_tools/ask_core.py` (question parsing and answers), `chalk_tools/ask_app.py` (Flask wrapper), `chalk_tools/deploy_ask.py` (deploy and smoke test). Redeploy after changing data or code: `uv run --with chalkcompute --with chalkpy python -m chalk_tools.deploy_ask`. Local run: `uv run --with flask python chalk_tools/ask_app.py`. Tests: `uv run --with pytest --with flask python -m pytest tests -q` (141 pass).

## Not done yet
The junk-band eval from `docs/chalk-teammates.md` (recommendations stay out of 750 to 850 km and dead-satellite lifetime under about 25 years) is not built on Chalk yet. The service is traced (`tracing` at 100%) but no monitors or dashboard exist.
