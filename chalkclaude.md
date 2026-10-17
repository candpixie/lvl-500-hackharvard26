# orbit-payback (working name)

HackHarvard 2026 (Oct 16-18). A simulation for putting items in space: pick an altitude and inclination
(maybe size), see where it sits among every tracked satellite and piece of debris on a 3D globe, how
crowded that shell is, what is nearby, and better spots. `README.md` has the pitch and MVP order.

Hook: SpaceX filed (Jan 30 2026) for up to 1 million orbital data center satellites; LEO holds about
29,000 tracked objects today. Sustainability angle: debris at 750-850 km that drag cannot clear.
The first direction (carbon payback of orbital data centers) is kept in `archive/carbon-payback/`.

## Prizes and hard requirements
- SpaceXAI "Make It Legendary": real space data, built in Cursor (keep a log of Cursor and Grok Bot use), Grok Imagine or Voice API.
- ASUS Sustainability track: space sustainability, long-lived debris.
- Chalk "Best Data-Driven Agent": an agent on real data, doing real work on Chalk, proven with evals.
- Deadlines: Sat 2pm everything connected end to end, Sat 6pm feature freeze, Sun 8am Devpost submission.

## Layout
- `pipeline/` Python, offline. `fetch_orbits.py` (download), `build_objects.py` (objects.json + close_approaches.json), `leo_shells.py` (counts per 50 km shell), `shadow.py` (older, carbon work).
- `data/out/` built data. Committed: `leo_shells.json`, `close_approaches.json`, `shadow.json`. Ignored: `objects.json` (14 MB, regenerate it).
- `data/raw/` downloads, gitignored, absent until you run the fetch.
- `docs/data.md` data inventory and gotchas.
- `web/` Vite + React + TypeScript frontend (globe.gl, three, satellite.js). `propagate.worker.ts` runs SGP4, `PlacePanel.tsx` + `shells.ts` + `place.ts` are the placement UI.
- `chalk-sandbox/` Chalk project (untracked so far). `archive/` old direction.

## Commands
Needs uv. From the repo root:
- `uv run python pipeline/fetch_orbits.py` then `build_objects.py` then `leo_shells.py`. CelesTrak blocks repeat downloads of a group for about 2 hours; the fetch script skips fresh files.
- Web, from `web/`: `npm run dev`, `npm run build`, `npm run lint`.

## Data facts and limits
- Orbits for 20,038 of 35,044 tracked objects. Rocket bodies: 12 of 2,297. About 9,900 debris pieces missing. Space-Track (free account) would fill this; read its user agreement first and never commit its data.
- Shell altitude is (apogee + perigee) / 2, a shell average. Fine for crowding, not for exact positions.
- SATCAT shell counts cover all 35k objects; the globe only draws the 20k with orbits. Label which one a number is.
- Nobody publishes positions; compute them with SGP4. Browser: satellite.js 6.0 or later (`json2satrec(obj.omm)`), run in a Web Worker, draw one GPU point cloud.
- SOCRATES: 195,841 predicted close approaches for 7 days; we keep the top 500 with same-constellation pairs and relative speed under 0.1 km/s removed. Check the SOCRATES format page before trusting MAX_PROB.

## Rules
- Say "crowding" or "close approach", never "collision probability" unless it is SOCRATES's own number.
- Every number on screen has a source. Fact-check anything that goes on a slide, including decay times.
- Grok image/video is illustration and labeled that way. Data is drawn from data.
- Never commit `data/raw/`, `objects.json`, Space-Track data, or `.env`.

## Chalk agent (draft design, team to confirm)
- Grok calls tools; tools return the numbers; Grok only quotes them and maps a mission to an orbit.
- All LLM use is Grok (answers, function calling, Voice, Imagine, any judge). Chalk's Model Gateway is not used. See `docs/split.md` for the two-person split and final tool signatures.
- Planned tools: `shell_crowding(altitude_km, inclination_deg=None)`, `objects_near(altitude_km, inclination_deg, limit)`, `close_approaches(min_altitude_km, max_altitude_km, limit)`, `recommend_orbit(mission)`. Not built yet; no Grok or Chalk agent code exists in the repo.
- Raw shell counts mislead across shells (higher shells have more volume); consider objects per km^3.
- Eval: agent sees only the first two tools; score its recommended shells by SOCRATES near-miss rate per shell against a random-pick baseline and the web app's lowest-count rule. Build the answer key from all 195,841 SOCRATES rows, not the 500 committed. The agent must never see `close_approaches` during the eval.
- Also test tool accuracy (pinned data snapshot, independent recompute, known objects like ISS 25544 and Sentinel-1A 39634; the NuSat-47 vs Fengyun-1C pair only existed in Friday's snapshot) and agent tool-calling (right tool, valid arguments, answer numbers match tool output).
- Chalk environment `spcwce09a241`. Sandboxes cost quota, keep lifetimes short. Pass `environment_id` on Chalk MCP calls. Open questions for the Chalk rep: hackathon access, Grok through the model gateway, template license.

## Observability (draft, nothing built yet; volumes and targets are estimates)
- One trace per user question, about 8-12 spans. Expect under ~2,500 traces over the weekend, so keep 100% (`tracing=True` on the agent function and every tool function; redeploy after changing it). Tag each trace `run.type` = demo | dev | eval.
- Chalk does not auto-instrument LLM calls: wrap each Grok and tool call in `chalkcompute.span()`. Traces appear on the function's Scaling Group page (Remote Call Traces). Whether code running outside Chalk can send traces to Chalk is unverified; ask the Chalk rep.
- Spans: `agent.answer` (root), `agent.plan`, `grok.call`, `tool.shell_crowding`, `tool.objects_near`, `tool.close_approaches`, `guard.check`, `tts.speak`, `ui.event`.
- Root attributes: question.id, question.text (<=200 chars, never audio), mode, run.type, eval.run_id, eval.row_id, data.snapshot_id, agent.version (git sha), model.name, result.status, tool_calls.count, tokens.total, answer.word_count.
- Tool spans: tool.name, tool.args (small JSON), result.rows, error.type, plus shell_km, coverage.share, or window.days per tool. Record args, counts and flags, not full results. Never log keys.
- `guard.check`: fidelity.ok (every answer number appears in tool output), banned_phrase.hit, coverage_disclosed, args_in_range.
- Logs: one JSON line per tool call and per answer, with trace_id and span_id, plus latency_ms and data.snapshot_id.
- The pipeline should write `data/out/manifest.json` (object counts, orbit epoch age, SOCRATES window, build time, file hashes); its id is `data.snapshot_id`. Not written yet.
- Targets: end-to-end p50 under 3 s and p95 under 6 s for voice; tool error rate under 2%; fidelity failures 0; at most 4 tool calls per answer.
- Chalk: 3 monitors (tool error rate, p95 latency, any fidelity failure) and 1 demo dashboard. Ask before creating them in the Chalk account. Never group or alert on free-text attributes.
- Evals: scorers can read a run's spans through the `Trace` argument (tool selection, call count, latency). Reads wait for span ingest to settle.

## API contract (draft, nothing built; verify the unverified items in the spike first)
- Flow: browser (text, later voice) -> `/api/ask` on a small server (middleware in `web/vite.config.ts`, holds the keys) -> Grok with function calling -> Chalk functions -> Grok writes the spoken answer -> server returns `{status, speak_text, display_text, ui_events[], evidence[], caveats[], trace_id, snapshot_id}`. Optional `/api/visual` (Grok Imagine illustration, after the answer, labeled, capped per session). `GET /api/manifest` gives the data snapshot for a "data as of" footer. `GET /api/health` pings Chalk and Grok.
- Request: `POST /api/ask {session_id, text, mode: text|voice, context: {altitude_km, inclination_deg, selected_norad}}`.
- Chalk functions, JSON in/out, stateless and deterministic per data snapshot: `shell_crowding`, `objects_near`, `close_approaches`, and `recommend_orbit(mission)`. `recommend_orbit` ranks shells by crowding density and `objects_near` only, never SOCRATES, so the eval against SOCRATES stays honest. This refines the Chalk agent draft above: Grok maps the mission and presents, Chalk decides. Results are `{ok, data, coverage, caveats, snapshot_id}` or `{ok:false, error:{type,message}}`.
- UI events: `focusOrbit{altitude_km, inclination_deg}`, `selectObject{norad}`, optional `showApproach{norad_1, norad_2}`. One `applyUiEvent` handler in `web/src/App.tsx`. Today the web app has no inclination state, no camera ref, no click handling, no NORAD ids from the worker, and does not serve `close_approaches.json`.
- Conversation state lives on the server, not Chalk: last 6 turns (question, speak_text, short evidence summary), focus, selected NORAD, last recommendations; 30 min TTL. Grok turns relative phrases into absolute args ("a bit higher" = +50 km; "that one" = selected object or top result); "why?" is answered from stored evidence.
- Fallback tiers: 0 live; 1 Grok down (templated answer from Chalk output, browser speech synthesis); 2 Chalk or network down (replay from `demo/cache.json`, recorded with server mode `record`; modes are `live | record | replay | auto`); 3 everything down (globe and panel run from local files, backup video). Timeouts: Chalk 5 s, Grok 8 s, about 10 s total.
- Always show a badge (live / degraded / replayed); never present a replay as live, and demo the live path with traces open for the Chalk judges. Add `answer.source` to the root span.
- Keys: gitignored `.env`, server-side only, never in `VITE_*` (bundled into the browser). Rate-limit per session and cap Imagine calls.
- Before the demo: health check, warm the Chalk functions, check credit balances, freeze the data snapshot (do not refetch CelesTrak), hotspot ready, test once with wifi off, backup video recorded before the Sat 6pm freeze.
- Spike first (about 30 min): call one Chalk function from a script; call Grok with a tool definition; time one Imagine request; ask the SpaceXAI and Chalk reps about hackathon keys and credits, and whether Chalk can call Grok.

## Working together
- One branch per person, PRs into `main`, one owner per folder.
- Python 3.11 or newer with uv. Commit messages are `type: summary` (`content:`, `config:`, `ui:`, `docs:`).
