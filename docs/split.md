# Work split for two people (Sat Oct 17, written 12:34 PM EDT)

Gates: Sat 2 PM everything connected end to end (even if ugly), Sat 6 PM feature freeze + backup video, Sun 8 AM Devpost.
Person A = Chalk side. Person B = Grok and web side. Names: A = ____, B = ____.

## Fixed decisions
- **All LLM use is Grok:** the user-facing answer, function calling, mission-to-orbit mapping, Voice, Imagine, and the optional explanation judge. We do not use Chalk's Model Gateway (it lists OpenAI, Anthropic and Gemini, not Grok).
- **Only non-Grok pieces:** Chalk's hard-coded scorers (plain Python, no LLM) and the browser speech synthesis used as a fallback when Grok is down.
- **Chalk runs real work:** the four functions below, the eval, and the traces. Chalk's `llm_judge` accepts `base_url` plus an `api_key` Secret for any OpenAI-compatible endpoint; if xAI's endpoint is OpenAI-compatible (unverified), Grok can be the judge. Otherwise skip the judge; the hard-coded scorers carry the eval.
- **No Sandbox per question.** `object_near` uses orbit elements (perigee, apogee, inclination), not SGP4, so nothing needs a cold-started sandbox. SGP4 stays in the browser worker for the globe. Revisit only if the spike shows sandboxes are fast.
- Cut for now: `object_story` (the click panel reads local SATCAT data), version-comparison slide, video until everything else works.

## Tools (Chalk functions, JSON in and out)
All return `{ok, data, coverage, caveats, snapshot_id}` or `{ok:false, error:{type,message}}`. Stateless and deterministic for a data snapshot.
1. `shell_crowding(altitude_km, inclination_deg=None)`: counts by type in the 50 km shell, objects per km^3, share with orbits. Check that SATCAT has an inclination column before relying on the inclination filter.
2. `objects_near(altitude_km, inclination_deg, limit=10)`: objects whose perigee-apogee range covers the altitude at a similar inclination, nearest first, with name, owner, launch year, type. Reports the coverage gap (12 of 2,297 rocket bodies have orbits).
3. `close_approaches(min_altitude_km, max_altitude_km, limit=10)`: real SOCRATES predictions for the one week we hold, filtered (same-constellation pairs and relative speed under 0.1 km/s removed), joined to altitude via SATCAT. No `week` argument: we only have one week.
4. `recommend_orbit(mission)`: ranks shells for a mission by density and `objects_near` only. It must never read SOCRATES, so the eval against SOCRATES stays honest. Does not claim decay times (unverified); uses debris share as the persistence proxy.

## Contract (agree first, 30 minutes, together)
- `POST /api/ask {session_id, text, mode, context{altitude_km, inclination_deg, selected_norad}}` returns `{status, speak_text, display_text, ui_events[], evidence[], caveats[], trace_id, snapshot_id}`. UI events: `focusOrbit{altitude_km, inclination_deg}`, `selectObject{norad}`, optional `showApproach`.
- Shared function signature: `run_agent(question, history, context)` in `agent/` returns `{tool_calls, answer, ui_events}`. B writes it; A imports it as the Chalk eval task.
- Deliverables of the 30 minutes: the spike results (call one Chalk function from a script; Grok with a tool definition; one Imagine timing; ask reps about keys and credits), `docs/api.md`, and a mock `/api/ask` with canned `ui_events`.

## Person A: Chalk, data, evals, observability
Owns `pipeline/`, `data/`, and a new `chalk_tools/` folder (functions, tests, evals).
- By 2 PM: data prep for the tools (shell density, altitude-joined close approaches, `data/out/manifest.json`); `shell_crowding` deployed on Chalk and callable.
- By 4 PM: `objects_near`, `close_approaches`, `recommend_orbit`; tool accuracy tests (below); `tracing=True` and spans.
- By 6 PM: SOCRATES answer key from all 195,841 rows; eval datasets and scorers; one eval run with a score and a random-pick baseline; one trace ready to show; record/replay cache generation for the demo questions; `/api/health` and `/api/manifest`.
- After 6 PM: monitors and dashboard (ask first), more eval rows.

## Person B: Grok, server, web
Owns `web/`, new `server/` and `agent/`.
- By 2 PM: mock `/api/ask` wired to the UI; `focusOrbit` moves the globe (add inclination state, camera ref, `applyUiEvent` in `web/src/App.tsx`).
- By 4 PM: real Grok loop with function calling against Chalk; session state and relative phrases ("a bit higher" = +50 km); chat box; `close_approaches.json` served by `web/vite.config.ts` if needed.
- By 6 PM: fallback tiers and the live/degraded/replayed badge; `guard.check` flags and span attributes; NORAD ids from the worker plus click-to-select; Grok Voice or Imagine (whichever is cheaper after the spike; the prize needs one); record the backup video.
- After 6 PM: polish, the other Grok media API if time.

## Evals (all hard-coded unless noted)
Headline, on Chalk (A):
- `shell_safety`: the shell `recommend_orbit` returns, scored by rank of its SOCRATES near-miss rate per object among all shells (0 to 1), against a random-pick baseline and against the web app's lowest-raw-count rule.
- `crowding_validity`: does the density index correlate with the SOCRATES near-miss rate per shell (rank correlation). Tests whether the index means anything.
- `mission_fit`: inclination within the range for the mission type (short hand-labeled list).
- `grounding`: every number in the answer appears in tool output. `guardrails`: no "safe", no "collision probability" unless quoting SOCRATES, empty regions say "no tracked objects", coverage gap disclosed. `json_valid`.
Tool accuracy (A, plain tests on a pinned snapshot): independent recompute and sums for `shell_crowding`; brute-force oracle and known objects (ISS 25544 at about 420 km and 51.6 degrees, Sentinel-1A 39634 at about 693 km and 98 degrees, plus negatives) for `objects_near`; independent re-filter, the NuSat-47 vs Fengyun-1C pair (66743 and 31441) ranked top, exclusions, km to meters for `close_approaches`.
Agent tool-calling (A writes rows, runs Grok loop from B): tool selection (`json_match`), arguments (`numeric_close`, unit conversion, mission phrases), no-call and out-of-scope rows, multi-step, error handling, paraphrases, multi-turn follow-ups, call budget. Two configurations: the headline eval hides `close_approaches` from the agent; the tool-calling eval exposes all tools but does not score shell choice against SOCRATES.
Optional Grok judge for explanation clarity, reported separately.

## Shared rules
One branch per person, PR into `main` about every 2 hours, one owner per folder. Keys in a gitignored `.env`, never in `VITE_*`. Fallbacks and honesty badge as in `chalkclaude.md`. Observability spans as in `chalkclaude.md`, with `answer.source` = live | degraded | replay.

## Verify before building
Chalk functions callable from a server; Grok tool-calling format and whether xAI's endpoint works with Chalk's `base_url` option; Imagine and Voice latency, cost and credits; SATCAT inclination column; whether `data/raw/` can be refetched without CelesTrak throttling.
