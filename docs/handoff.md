# Handoff: read this first (Sat Oct 17, 12:45 PM EDT)

> **Status update (Sat afternoon):** parts of this document are superseded. The team built `api/` (FastAPI, port 8000, `/ask`), the Grok loop (`api/agent.py`, importable as `from agent import run_agent`), and a placement model (`pipeline/orbit_data.py`, `pipeline/scoring.py`). The "Python server in `server/` on port 8787" and `/api/ask` shapes below were an earlier proposal and are withdrawn; use `docs/chalk-contract.md` and `docs/chalk-teammates.md`. The Chalk functions section still applies (see `docs/api.md`).


This is the one document that explains the project, what exists, what we decided, and what to do next. `chalkclaude.md` (repo root) is the same material in a terse form for Claude. It is named `chalkclaude.md` so it does not overwrite anyone's own `CLAUDE.md`; Claude Code only auto-loads a file named `CLAUDE.md`, so add `@chalkclaude.md` to your own `CLAUDE.md` or ask Claude to read it. `docs/split.md` is the two-person work split. `docs/data.md` is the data inventory. `README.md` is the pitch.

## 1. What we are building
A simulation for putting items in space. The user picks an altitude and inclination (maybe size) and sees where it sits among every tracked satellite and piece of debris on a 3D globe, how crowded that orbital shell is, what is nearby, and better spots. A Grok agent (text or voice) answers questions with real numbers and flies the globe to the answer.

Why now: SpaceX filed (Jan 30 2026) for up to 1 million orbital data center satellites, and low Earth orbit holds about 29,000 tracked objects today. Debris piles up at 750 to 850 km, where air drag cannot clear it for a very long time; working satellites crowd 450 to 500 km. Example from Friday night's SOCRATES file: NuSat-47 predicted to pass 12 m from a Fengyun-1C debris piece at 14.5 km/s on Oct 22. That pair is NOT in the current snapshot (the 7-day window rolled forward), so do not cite it as current; pick an example from `data/out/close_approaches.json` and verify it before using on a slide.

History: our first idea was whether an orbital data center pays back its carbon debt. We switched to the placement simulation. The old work is in `archive/carbon-payback/`.

## 2. Prizes and hard requirements (HackHarvard 2026, Oct 16 to 18)
- **SpaceXAI "Make It Legendary":** real space data; built with Cursor (keep a log of Cursor and Grok Bot use); must use Grok Imagine or Grok Voice.
- **ASUS Sustainability track:** space sustainability, long-lived debris. Optional ASUS content challenge (post about the build): ask at the venue.
- **Chalk "Best Data-Driven Agent":** an agent on real data that does real work on Chalk, judged on impact, use of data and how rigorously we evaluate it.
- Everything LLM-related is **Grok**. We do not use Chalk's Model Gateway (it lists OpenAI, Anthropic and Gemini, not Grok).
- **Deadlines:** Sat 2 PM everything connected end to end (even if ugly); Sat 6 PM feature freeze and record the backup video; Sun 8 AM Devpost submission. Confirm at the venue that one team can enter a track plus several challenges.

## 3. What exists today (honest status)
- **Data pipeline (`pipeline/`):** `fetch_orbits.py` downloads CelesTrak data; `build_objects.py` writes `data/out/objects.json` (20,038 objects with orbits, 14 MB, gitignored) and `close_approaches.json` (top 500); `leo_shells.py` counts objects per 50 km shell. `data/raw/` is gitignored and absent until you run the fetch.
- **Web app (`web/`, Vite + React + TypeScript, globe.gl, three, satellite.js):** a 3D globe with all objects as one GPU point cloud (SGP4 in a Web Worker), an altitude slider that highlights the shell, a panel with the shell count and majority type, and a debris-only toggle. It has no inclination, no click-to-select, no NORAD ids from the worker, no chat, no voice, no API calls, and does not serve `close_approaches.json`.
- **Not built at all:** the Grok agent, the server route, the Chalk functions, the evals, tracing, fallbacks.
- **Chalk:** one person's CLI is installed and logged in, MCP is registered with Claude Code, and a hello-world sandbox ran. The Chalk project is not shared with you yet (see section 9).

## 4. Data facts and limits
- 35,044 tracked objects in orbit (20,149 payloads, 12,543 debris, 2,297 rocket bodies); 29,211 in LEO; 11,154 are Starlink. We have orbits for only 20,038 of them: 16,753 satellites, 2,679 debris, **12 rocket bodies**, 594 unidentified. Roughly 9,900 debris pieces are missing. Space-Track (free account) would fill the gap; read its user agreement first and never commit its data.
- Shell altitude is (apogee + perigee) / 2, a shell average. Fine for crowding, not exact positions. SATCAT counts (35k) differ from globe dots (20k); label which one a number is.
- SOCRATES: 195,841 predicted close approaches for 7 days (Oct 16 to 22). We keep the closest 500 with same-constellation pairs and relative speed under 0.1 km/s removed (Starlink vs Starlink shows probability 1.0, probably a modeling artifact). Check the SOCRATES format page before trusting max probability.
- Nobody publishes positions; compute with SGP4. Browser: satellite.js 6.0 or later (`json2satrec`), in a Web Worker, one GPU point cloud.
- CelesTrak blocks repeat downloads of the same group for about 2 hours. Fetch once, freeze the snapshot for the demo, and do not refetch during it.
- Rules: say "crowding" or "close approach", never "collision probability" unless quoting SOCRATES. Every number on screen has a source. Grok media is illustration and is labeled so. Verify decay times before any slide.

## 5. Architecture
Browser (text, later voice) -> `/api/ask` on a small **Python** server in `server/` (Vite proxies `/api` to it; holds the keys; see `docs/api.md` for why it is Python and not a Vite middleware) -> Grok with function calling -> Chalk functions -> Grok writes the spoken answer -> server returns `{status, speak_text, display_text, ui_events[], evidence[], caveats[], trace_id, snapshot_id}` -> browser plays voice and applies UI events. Optional `/api/visual` asks Grok Imagine for an illustration after the answer, never blocking it. Also `GET /api/manifest` ("data as of") and `GET /api/health`.

Request: `POST /api/ask {session_id, text, mode: text|voice, context: {altitude_km, inclination_deg, selected_norad}}`.

UI events: `focusOrbit{altitude_km, inclination_deg}`, `selectObject{norad}`, optional `showApproach{norad_1, norad_2}`.

**Chalk functions (JSON in, JSON out; stateless and deterministic per data snapshot)**, each returning `{ok, data, coverage, caveats, snapshot_id}` or `{ok:false, error:{type,message}}`:
1. `shell_crowding(altitude_km, inclination_deg=None)`: counts by type, objects per km^3, share with orbits.
2. `objects_near(altitude_km, inclination_deg, limit)`: objects whose orbit range covers the altitude at a similar inclination (from orbit elements, no SGP4), with name, owner, launch year, type, and the coverage gap.
3. `close_approaches(min_altitude_km, max_altitude_km, limit)`: filtered SOCRATES rows joined to altitude. One week of data only.
4. `recommend_orbit(mission)`: ranks shells by density and `objects_near` only. It must never read SOCRATES, or the eval is circular.

**Conversation state** lives on the server, not Chalk: last 6 turns, current focus, selected NORAD, last recommendations, 30 minute TTL. Grok turns relative phrases into absolute arguments before calling tools ("a bit higher" is plus 50 km; "that one" is the selected object or top result); "why?" is answered from stored evidence.

**Fallback tiers:** 0 live. 1 Grok down: templated answer from Chalk output, spoken with browser speech synthesis. 2 Chalk or network down: replay recorded answers from `demo/cache.json` (server modes `live | record | replay | auto`). 3 everything down: globe, panel and counts run from local files, plus the backup video. Timeouts: Chalk 5 s, Grok 8 s, about 10 s total. Always show a live / degraded / replayed badge, and never present a replay as live. For the Chalk judges, demo the live path with a trace open.

**Keys:** gitignored `.env`, server-side only, never in `VITE_*` (Vite bundles those into the browser). Rate-limit per session; cap Imagine calls.

## 6. Evals (Chalk Agent Evals: dataset rows, a task function, scorers returning 0 to 1)
Headline (hard-coded, no LLM): `shell_safety` scores the shell `recommend_orbit` returns by the rank of its SOCRATES near-miss rate per object among all shells, against a random-pick baseline and against the web app's current lowest-raw-count rule. Build the answer key from all 195,841 SOCRATES rows, not the 500 committed, and keep `close_approaches` hidden from the agent in this eval. Also `crowding_validity` (does the density index correlate with near-miss rate), `mission_fit` (inclination within a hand-labeled range, for example 96 to 99 degrees for sun-synchronous), `grounding` (every number in the answer appears in tool output), `guardrails` (no "safe", no "collision probability", empty regions say "no tracked objects", coverage gap disclosed), `json_valid`. An optional Grok judge for explanation clarity, reported separately.

Tool accuracy (plain tests on a pinned data snapshot): recompute `shell_crowding` independently and check sums and edges; check `objects_near` against a brute-force oracle plus known objects (ISS 25544 at about 420 km and 51.6 degrees, Sentinel-1A 39634 at about 693 km and 98 degrees, and negatives); re-filter SOCRATES independently, check the closest filtered row ranks top (the NuSat-47 vs Fengyun-1C pair, 66743 and 31441, was only in Friday's snapshot; use it only from a pinned fixture), exclusions hold, and 0.012 km shows as 12 meters.

Agent tool-calling (Chalk eval; agent output includes `tool_calls` and `answer`): tool selection, arguments (tolerance about 25 km and 2 degrees; unit conversion; mission phrases), no-call and out-of-scope rows, multi-step, error handling, paraphrases, multi-turn follow-ups, call budget. Rough pass bars (our estimates): 95% selection, 90% arguments, 100% fidelity.

Known limit: a true time-correct eval needs historical snapshots we do not have.

## 7. Tracing and observability (Chalk)
One trace per question, about 8 to 12 spans, 100% sampling (`tracing=True` on the agent and each tool function; redeploy after changing it). Chalk does not auto-instrument LLM calls, so wrap each Grok and tool call in `chalkcompute.span()`. Tag every trace `run.type` = demo | dev | eval, plus `answer.source` = live | degraded | replay. Spans: `agent.answer` (root), `agent.plan`, `grok.call`, `tool.shell_crowding`, `tool.objects_near`, `tool.close_approaches`, `guard.check`, `tts.speak`, `ui.event`. Record arguments, counts and flags, never full results, keys or audio. One JSON log line per tool call and per answer with trace id. The pipeline writes `data/out/manifest.json` (counts, orbit epoch age, SOCRATES window, hashes); its id is `data.snapshot_id`. Targets (our estimates): end-to-end p50 under 3 s, p95 under 6 s; tool error rate under 2%; fidelity failures 0; at most 4 tool calls per answer. Three monitors and one dashboard in Chalk; ask before creating them in the account.

## 8. Who does what
See `docs/split.md`. Person A: Chalk functions, data prep, evals, observability, record/replay cache. Person B: Grok loop, server, UI events, fallbacks, voice or video. Together first: the 30 minute spike, `docs/api.md`, and a mock `/api/ask` so both can work in parallel. Agreed hand-off: B writes `run_agent(question, history, context)` in `agent/`; A imports it as the Chalk eval task.

Cut list if time is short: `object_story`, video, Sandbox execution, version-comparison slide.

## 9. Getting set up
- **Repo:** `uv sync` (Python 3.11+), then `uv run python pipeline/fetch_orbits.py`, `build_objects.py`, `leo_shells.py`. Web: `cd web && npm install && npm run dev`.
- **Chalk access:** the Chalk project belongs to one teammate's account. Ask them to invite you from the dashboard (Settings, Users and roles). Then install the CLI (`curl -s -L https://api.chalk.ai/install.sh | sh`, add `~/.chalk/bin` to PATH), run `chalk login` (approve the link in a browser signed in to the right account; approving from the wrong account just logs you into the wrong project), and `chalk init` in a project folder. To let Claude Code use Chalk: `chalk mcp configure-claude`. The Chalk project environment id is `spcwce09a241`; pass it when calling Chalk tools. Sandboxes and functions use quota; keep lifetimes short.
- **Grok keys and credits:** not set up yet. Ask the SpaceXAI team (workshop Sat 1:30 to 2:30 PM). Keys go in `.env`.
- **Chalk docs:** https://docs.chalk.ai (evaluations, scorers, tracing, functions).

## 10. Open and unverified (check in the first 30 minutes)
- Can a deployed Chalk function be called from our server? (`RemoteFunction.from_name`, default 60 s timeout.)
- Grok's tool-calling format; whether Chalk can call Grok from inside a function; whether xAI's endpoint works with Chalk's `llm_judge` `base_url` option.
- Grok Voice and Imagine: latency, cost, credits; realtime voice auth from the browser; browser speech synthesis quality on the demo machine.
- Does SATCAT have an inclination column (needed for the inclination filter)? `data/raw/` is not on every machine, so check after fetching.
- Hackathon access or credits from Chalk (chalk.ai/hackharvard, Chalk Slack channel) and whether their demo templates are free to copy.
- Who owns each piece, and whether the carbon-payback work stays archived.

## 11. Glossary
LEO: low Earth orbit, under 2,000 km. Shell: a 50 km altitude band. NORAD id: the catalog number of an object. SATCAT: the catalog of every tracked object (type, owner, launch, altitude). OMM/TLE: orbit element formats. SGP4: the standard model that turns orbit elements into positions. SOCRATES: CelesTrak's daily predicted close approaches. RAAN: the rotation of an orbit plane (the app hardcodes 28 degrees for now).
