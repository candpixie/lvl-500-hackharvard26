"""Grok is the front door (STT, TTS, Imagine). Chalk does reasoning; local tools are fallback."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from openai import OpenAI

from api.chalk import (
    REMOTE_FUNCTIONS,
    ask_chalk,
    call_remote,
    chalk_ok,
    enabled as chalk_enabled,
    redact,
    remote_functions_enabled,
)
from api.data import (
    DEFAULT_DIMS_M,
    DEFAULT_INC_DEG,
    focus_from_place,
    focus_from_rank,
    get_close_approaches,
    get_shell_crowding,
    place_satellites,
    rank_shells,
)

XAI_BASE = "https://api.x.ai/v1"
ASK_MODEL = os.getenv("XAI_ASK_MODEL", "grok-4.20-0309-non-reasoning")
VOICE_ID = os.getenv("XAI_VOICE_ID", "eve")
STT_MODEL = os.getenv("XAI_STT_MODEL", "grok-voice-transcribe-2.0")
IMAGINE_MODEL = os.getenv("XAI_IMAGINE_MODEL", "grok-imagine-image-2.0")
MAX_TOOL_ROUNDS = 6

SYSTEM_BASE = """You are the Orbit Payback voice. You help someone pick a low Earth orbit that does the least harm.

Rules:
- Answer ONLY from tool results. Quote the actual numbers the tools returned.
- Every risk number is tracked objects only, a lower bound. Say that once.
- Say "crowding" or "close approach". Never say "collision probability" unless you are quoting SOCRATES max_probability.
- "Expected collisions per year (first-order model)" is the correct label for our rate.
- Do not claim orbital data centers are greener than Earth ones. Angle: if we build in orbit, where does it do the least harm?
- Do not frame SpaceX as a villain. Neutral: where to build safely.
- Keep the spoken answer to about 3 short sentences.
- Default satellite size is 4 x 2 x 1 meters unless the user says otherwise.
"""

SYSTEM_CHALK = SYSTEM_BASE + """
You MUST call ask_chalk first with the user's question. Chalk owns data and conclusions.
If ask_chalk returns an answer and numbers, do not call any other tool. Speak those numbers. Use its focus.
If ask_chalk returns an error or fallback=true, then you may use the local tools:
  rank_shells for "where should I put N",
  place_satellites for a specific altitude,
  get_shell_crowding + get_close_approaches for 800 km / debris,
  get_close_approaches with no altitude for the closest near miss this week.
"""

SYSTEM_LOCAL = SYSTEM_BASE + """
Call rank_shells for "where should I put N".
Call place_satellites for a specific altitude.
Call get_shell_crowding and get_close_approaches around 800 km for debris questions.
Call get_close_approaches without an altitude for the closest near miss this week.
"""

SYSTEM_REMOTE = """
Deployed Chalk functions, when CHALK_REMOTE_FUNCTIONS is on:
  shell_crowding for a 50 km shell,
  objects_near for who shares an altitude and inclination,
  close_approaches for SOCRATES rows in a band (200 km up to but not including 2000 km; use 200 and 1999 for the closest this week).
Prefer those over get_shell_crowding and get_close_approaches.
rank_shells and place_satellites stay local until recommend_orbit exists. Use them for where to put satellites and for a specific altitude.
If a Chalk function returns ok=false or fallback=true, use the local tool with the same job.
"""

REMOTE_TOOLS = [
    {
        "type": "function",
        "name": "shell_crowding",
        "description": (
            "Chalk. Tracked-object counts in the 50 km shell that contains altitude_km. "
            "Optional inclination_deg filters to a band. Returns ok, data, coverage, caveats, snapshot_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "altitude_km": {"type": "number"},
                "inclination_deg": {"type": "number"},
            },
            "required": ["altitude_km"],
        },
    },
    {
        "type": "function",
        "name": "objects_near",
        "description": (
            "Chalk. Tracked objects whose perigee-apogee range covers altitude_km at a similar inclination. "
            "Not a distance or collision estimate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "altitude_km": {"type": "number"},
                "inclination_deg": {"type": "number"},
                "limit": {"type": "integer"},
            },
            "required": ["altitude_km", "inclination_deg"],
        },
    },
    {
        "type": "function",
        "name": "close_approaches",
        "description": (
            "Chalk. SOCRATES close approaches whose pair altitude is inside the band. "
            "Quote max_probability only as SOCRATES's number. Band is 200 km inclusive to 2000 km exclusive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "min_altitude_km": {"type": "number"},
                "max_altitude_km": {"type": "number"},
                "limit": {"type": "integer"},
            },
            "required": ["min_altitude_km", "max_altitude_km"],
        },
    },
]

LOCAL_TOOLS = [
    {
        "type": "function",
        "name": "get_shell_crowding",
        "description": "LOCAL FALLBACK. Tracked-object counts for the 50 km shell that contains alt_km.",
        "parameters": {
            "type": "object",
            "properties": {"alt_km": {"type": "number"}},
            "required": ["alt_km"],
        },
    },
    {
        "type": "function",
        "name": "place_satellites",
        "description": "LOCAL FALLBACK. Score a placement 0-100 (higher = safer).",
        "parameters": {
            "type": "object",
            "properties": {
                "alt_km": {"type": "number"},
                "inc_deg": {"type": "number"},
                "dims_m": {"type": "array", "items": {"type": "number"}},
                "count": {"type": "integer"},
            },
            "required": ["alt_km", "count"],
        },
    },
    {
        "type": "function",
        "name": "rank_shells",
        "description": "LOCAL FALLBACK. Safest 50 km shells from 500 to 2000 km.",
        "parameters": {
            "type": "object",
            "properties": {
                "dims_m": {"type": "array", "items": {"type": "number"}},
                "count": {"type": "integer"},
                "top": {"type": "integer"},
            },
            "required": ["count"],
        },
    },
    {
        "type": "function",
        "name": "get_close_approaches",
        "description": "LOCAL FALLBACK. SOCRATES close approaches. Omit alt_km for the closest overall.",
        "parameters": {
            "type": "object",
            "properties": {"alt_km": {"type": "number"}, "limit": {"type": "integer"}},
        },
    },
]

CHALK_TOOL = {
    "type": "function",
    "name": "ask_chalk",
    "description": (
        "Primary reasoner. Sends the user question to Chalk, which runs SATCAT/SOCRATES "
        "resolvers and returns answer, focus, and sources. Call this first."
    ),
    "parameters": {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
}


def _client() -> OpenAI:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is not set")
    return OpenAI(api_key=key, base_url=XAI_BASE)


def has_xai_key() -> bool:
    return bool(os.getenv("XAI_API_KEY"))


def _num(value, default=None):
    if value is None or value == "":
        return default
    return float(value)


def _int(value, default=None):
    n = _num(value, default)
    return default if n is None else int(n)


def _system(use_chalk: bool, use_remote: bool) -> str:
    text = SYSTEM_CHALK if use_chalk else SYSTEM_LOCAL
    if use_remote:
        text += SYSTEM_REMOTE
    return text


def _tools(use_chalk: bool, use_remote: bool) -> list[dict]:
    tools: list[dict] = []
    if use_chalk:
        tools.append(CHALK_TOOL)
    if use_remote:
        tools.extend(REMOTE_TOOLS)
    tools.extend(LOCAL_TOOLS)
    return tools


def _run_tool(name: str, args: dict) -> Any:
    if name == "ask_chalk":
        return ask_chalk(str(args.get("question") or ""))
    if name in REMOTE_FUNCTIONS:
        return call_remote(name, args)
    if name == "get_shell_crowding":
        return get_shell_crowding(_num(args["alt_km"]))
    if name == "place_satellites":
        dims = args.get("dims_m") or DEFAULT_DIMS_M
        return place_satellites(
            _num(args["alt_km"]),
            _num(args.get("inc_deg"), DEFAULT_INC_DEG),
            [float(x) for x in dims],
            _int(args["count"]),
        )
    if name == "rank_shells":
        dims = args.get("dims_m") or DEFAULT_DIMS_M
        return rank_shells([float(x) for x in dims], _int(args["count"]), _int(args.get("top"), 10))
    if name == "get_close_approaches":
        return get_close_approaches(_num(args.get("alt_km")), _int(args.get("limit"), 10))
    return {"error": f"unknown tool {name}"}


def _text_from_response(response) -> str:
    chunks = []
    for item in response.output or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in item.content or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _focus_from_calls(tool_calls: list[dict]) -> dict | None:
    rank_focus = None
    place_focus = None
    other = None
    for call in tool_calls:
        name, result = call["name"], call["result"]
        if name == "ask_chalk" and chalk_ok(result):
            raw = result.get("focus")
            if isinstance(raw, dict) and raw.get("altitude_km") is not None:
                return {
                    "altitude_km": raw["altitude_km"],
                    "inclination_deg": raw.get("inclination_deg", DEFAULT_INC_DEG),
                }
            nested = result.get("tool_calls") or []
            if isinstance(nested, list):
                found = _focus_from_calls(nested)
                if found:
                    return found
        if name == "rank_shells" and isinstance(result, list):
            rank_focus = focus_from_rank(result) or rank_focus
        elif name == "place_satellites" and isinstance(result, dict) and "alt_km" in result:
            place_focus = focus_from_place(result)
        elif name == "get_shell_crowding" and isinstance(result, dict) and "alt_lo" in result and other is None:
            other = {
                "altitude_km": (result["alt_lo"] + result["alt_hi"]) / 2,
                "inclination_deg": DEFAULT_INC_DEG,
            }
        elif name == "get_close_approaches" and isinstance(result, dict) and result.get("rows") and other is None:
            row = result["rows"][0]
            alt = row.get("mean_alt_km") or row.get("alt_km_1") or row.get("alt_km_2")
            if alt is not None:
                other = {"altitude_km": alt, "inclination_deg": DEFAULT_INC_DEG}
        elif name in REMOTE_FUNCTIONS and other is None:
            other = _focus_from_remote(name, result)
    return rank_focus or place_focus or other


def _focus_from_remote(name: str, result: Any) -> dict | None:
    if not isinstance(result, dict) or result.get("ok") is False or result.get("fallback"):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    if name == "shell_crowding":
        shell = data.get("shell_km")
        if isinstance(shell, list) and len(shell) == 2:
            return {
                "altitude_km": (float(shell[0]) + float(shell[1])) / 2,
                "inclination_deg": DEFAULT_INC_DEG,
            }
    if name == "objects_near":
        query = data.get("query") if isinstance(data.get("query"), dict) else {}
        alt = query.get("altitude_km")
        if alt is not None:
            return {
                "altitude_km": alt,
                "inclination_deg": query.get("inclination_deg", DEFAULT_INC_DEG),
            }
    if name == "close_approaches":
        rows = data.get("approaches")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            alt = rows[0].get("pair_altitude_km")
            if alt is not None:
                return {"altitude_km": alt, "inclination_deg": DEFAULT_INC_DEG}
    return None


def _reasoner(tool_calls: list[dict]) -> str:
    chalk_calls = [c for c in tool_calls if c["name"] == "ask_chalk"]
    remote_calls = [c for c in tool_calls if c["name"] in REMOTE_FUNCTIONS]
    local_calls = [c for c in tool_calls if c["name"] not in {"ask_chalk", *REMOTE_FUNCTIONS}]
    chalk_live = bool(chalk_calls) and chalk_ok(chalk_calls[-1]["result"])
    remote_live = any(isinstance(c["result"], dict) and c["result"].get("ok") and not c["result"].get("fallback") for c in remote_calls)
    if (chalk_live or remote_live) and not local_calls:
        return "chalk"
    if chalk_calls or remote_calls:
        return "local_fallback"
    return "local"


def _history_messages(history: list | None) -> list[dict[str, str]]:
    """In-request turns only. Nothing is stored."""
    if not isinstance(history, list):
        return []
    messages: list[dict[str, str]] = []
    for turn in history[-6:]:
        if not isinstance(turn, dict):
            continue
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            messages.append({"role": str(turn["role"]), "content": str(turn["content"])[:2000]})
            continue
        question = turn.get("question")
        answer = turn.get("answer")
        if question:
            messages.append({"role": "user", "content": str(question)[:2000]})
        if answer:
            messages.append({"role": "assistant", "content": str(answer)[:2000]})
    return messages


def _context_note(context: dict | None) -> str:
    if not isinstance(context, dict):
        return ""
    bits = []
    for key in ("altitude_km", "inclination_deg", "selected_norad"):
        value = context.get(key)
        if value is None or value == "":
            continue
        bits.append(f"{key}={str(value)[:40]}")
    return ", ".join(bits)


def _input_messages(system: str, question: str, history: list | None, context: dict | None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(_history_messages(history))
    user = question
    note = _context_note(context)
    if note:
        user = f"{question}\n\nContext: {note}"
    messages.append({"role": "user", "content": user})
    return messages


def _ui_events_from_focus(focus: dict | None, tool_calls: list[dict] | None = None) -> list[dict]:
    events: list[dict] = []
    if isinstance(focus, dict) and focus.get("altitude_km") is not None:
        events.append({
            "type": "focusOrbit",
            "altitude_km": float(focus["altitude_km"]),
            "inclination_deg": float(focus.get("inclination_deg", DEFAULT_INC_DEG)),
        })
    for call in tool_calls or []:
        if call.get("name") != "get_close_approaches":
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        rows = result.get("rows") or []
        if not rows:
            continue
        norad = rows[0].get("norad_1")
        if norad is not None:
            events.append({"type": "selectObject", "norad": int(norad)})
        break
    return events


def ui_events_for(result: dict) -> list[dict]:
    focus = result.get("focus") if isinstance(result, dict) else None
    tool_calls = result.get("tool_calls") if isinstance(result, dict) else None
    if not isinstance(tool_calls, list):
        tool_calls = None
    return _ui_events_from_focus(focus if isinstance(focus, dict) else None, tool_calls)


def _pack_ask(answer: str, focus: dict | None, tool_calls: list[dict], reasoner: str) -> dict:
    public_calls = [
        {"name": c["name"], "arguments": c.get("arguments") or {}, "result": c.get("result")}
        for c in tool_calls
    ]
    return {
        "answer": answer,
        "focus": focus,
        "ui_events": _ui_events_from_focus(focus, tool_calls),
        "tool_calls": public_calls,
        "reasoner": reasoner,
    }


def _context_inc(context: dict | None) -> float:
    if not context:
        return DEFAULT_INC_DEG
    value = context.get("inclination_deg")
    try:
        return float(value) if value is not None else DEFAULT_INC_DEG
    except (TypeError, ValueError):
        return DEFAULT_INC_DEG


def _local_route(question: str, context: dict | None) -> tuple[str, list[dict]]:
    """Route demo-style questions to local tools. Returns (answer, tool_calls)."""
    q = question.lower()
    inc = _context_inc(context)
    tool_calls: list[dict] = []

    def record(name: str, args: dict, result: Any) -> Any:
        tool_calls.append({"name": name, "arguments": args, "result": result})
        return result

    if "near miss" in q or ("closest" in q and ("miss" in q or "approach" in q)):
        result = record("get_close_approaches", {"limit": 5}, get_close_approaches(None, 5))
        rows = result.get("rows") or []
        if not rows:
            return (
                "I have no filtered SOCRATES close approaches in this snapshot. Tracked objects only, lower bound.",
                tool_calls,
            )
        row = rows[0]
        miss_m = float(row["miss_distance_km"]) * 1000
        answer = (
            f"Closest predicted close approach this week is {row['name_1']} and {row['name_2']}, "
            f"about {miss_m:.0f} meters apart at {row['relative_speed_km_s']} km/s "
            f"({row['time_utc']}). Tracked objects only, lower bound."
        )
        return answer, tool_calls

    if "800" in q or "debris" in q or "junk" in q:
        crowd = record("get_shell_crowding", {"alt_km": 825}, get_shell_crowding(825))
        approaches = record(
            "get_close_approaches",
            {"alt_km": 825, "limit": 3},
            get_close_approaches(825, 3),
        )
        total = crowd.get("total") or crowd.get("PAY", 0) + crowd.get("DEB", 0) + crowd.get("R/B", 0)
        deb = crowd.get("DEB", 0)
        answer = (
            f"Around 800 to 850 km the catalog shows about {total} tracked objects, "
            f"including about {deb} debris pieces in that shell. "
            f"Drag is weak there, so junk stays up a long time. "
            f"I also see {approaches.get('count', 0)} close approaches near that band. "
            "Tracked objects only, lower bound."
        )
        return answer, tool_calls

    if "900" in q and ("million" in q or "1m" in q or "1,000,000" in q or "1000000" in q):
        result = record(
            "place_satellites",
            {"alt_km": 900, "inc_deg": inc, "dims_m": DEFAULT_DIMS_M, "count": 1_000_000},
            place_satellites(900, inc, DEFAULT_DIMS_M, 1_000_000),
        )
        answer = (
            f"Putting one million 4x2x1 m satellites at 900 km scores about {result['score']} out of 100 "
            f"(higher is safer). Expected collisions per year (first-order model) is about "
            f"{result['collisions_per_year']}, and a dead satellite stays up roughly "
            f"{result['dead_sat_lifetime_years']} years. Tracked objects only, lower bound."
        )
        return answer, tool_calls

    # Default: "where should I put N" / ranking
    count = 1000
    for token in ("1,000,000", "1000000", "1m", "million"):
        if token in q.replace(" ", ""):
            count = 1_000_000
            break
    else:
        if "1000" in q.replace(",", "") or "1,000" in q:
            count = 1000
    rows = record(
        "rank_shells",
        {"dims_m": DEFAULT_DIMS_M, "count": count, "top": 5},
        rank_shells(DEFAULT_DIMS_M, count, 5),
    )
    if not rows:
        return "I could not rank shells from this catalog snapshot.", tool_calls
    top = rows[0]
    mid = top["alt_lo"] + (top["alt_hi"] - top["alt_lo"]) / 2
    answer = (
        f"For {count:,} four-meter-class satellites, the safest shell I get is about "
        f"{top['alt_lo']:.0f} to {top['alt_hi']:.0f} km (midpoint {mid:.0f} km), "
        f"score about {top['score']} out of 100. {top.get('reason', '')} "
        "Tracked objects only, lower bound."
    )
    return answer, tool_calls


def ask_without_grok(question: str, context: dict | None = None) -> dict:
    """Chalk-first ask when Grok is unavailable. Local tools if Chalk is unset or errors."""
    q = (question or "").strip()
    if not q:
        return _pack_ask("Ask a question about where to place satellites.", None, [], "local")

    if chalk_enabled():
        result = ask_chalk(q)
        tool_calls = [{"name": "ask_chalk", "arguments": {"question": q}, "result": result}]
        if chalk_ok(result) and result.get("answer"):
            focus = None
            raw = result.get("focus")
            if isinstance(raw, dict) and raw.get("altitude_km") is not None:
                focus = {
                    "altitude_km": raw["altitude_km"],
                    "inclination_deg": raw.get("inclination_deg", DEFAULT_INC_DEG),
                }
            nested = result.get("tool_calls")
            if isinstance(nested, list):
                tool_calls.extend(
                    c for c in nested if isinstance(c, dict) and c.get("name")
                )
            return _pack_ask(str(result["answer"]), focus, tool_calls, "chalk")
        # fall through to local

    answer, tool_calls = _local_route(q, context)
    focus = _focus_from_calls(tool_calls)
    reasoner = "local_fallback" if chalk_enabled() else "local"
    return _pack_ask(answer, focus, tool_calls, reasoner)


def ask(question: str, history: list | None = None, context: dict | None = None) -> dict:
    if not has_xai_key():
        return ask_without_grok(question, context)

    client = _client()
    use_chalk = chalk_enabled()
    use_remote = remote_functions_enabled()
    tools = _tools(use_chalk, use_remote)
    tool_calls: list[dict] = []
    first_choice: Any = {"type": "function", "name": "ask_chalk"} if use_chalk else "auto"
    response = client.responses.create(
        model=ASK_MODEL,
        input=_input_messages(_system(use_chalk, use_remote), question, history, context),
        tools=tools,
        tool_choice=first_choice,
    )

    for _ in range(MAX_TOOL_ROUNDS):
        pending = [item for item in (response.output or []) if getattr(item, "type", None) == "function_call"]
        if not pending:
            break
        outputs = []
        for item in pending:
            args = json.loads(item.arguments or "{}")
            if item.name == "ask_chalk" and not args.get("question"):
                args["question"] = question
            try:
                result = _run_tool(item.name, args)
            except Exception as exc:
                chalk_tool = item.name == "ask_chalk" or item.name in REMOTE_FUNCTIONS
                result = {"error": redact(str(exc)), "fallback": chalk_tool}
            tool_calls.append({"name": item.name, "arguments": args, "result": result})
            outputs.append({
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(result, default=str),
            })
        next_choice = "auto"
        if use_chalk and any(c["name"] == "ask_chalk" and chalk_ok(c["result"]) for c in tool_calls):
            next_choice = "none"
        response = client.responses.create(
            model=ASK_MODEL,
            input=outputs,
            tools=tools,
            tool_choice=next_choice,
            previous_response_id=response.id,
        )

    answer = _text_from_response(response)
    if not answer:
        for call in reversed(tool_calls):
            if call["name"] == "ask_chalk" and chalk_ok(call["result"]) and call["result"].get("answer"):
                answer = call["result"]["answer"]
                break
    if not answer:
        answer = "I could not get a number-backed answer. Try asking about a shell or a count."
    focus = _focus_from_calls(tool_calls)
    return _pack_ask(answer, focus, tool_calls, _reasoner(tool_calls))


def run_agent(question: str, history: list | None = None, context: dict | None = None) -> dict:
    """Eval entrypoint. Same loop as ask(). history and context are not stored."""
    return ask(question, history=history, context=context)


def speak(text: str) -> bytes:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is not set")
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{XAI_BASE}/tts",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"text": text, "voice_id": VOICE_ID, "language": "en"},
        )
        response.raise_for_status()
        return response.content


def transcribe(audio: bytes, filename: str = "clip.webm", content_type: str = "audio/webm") -> str:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is not set")
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{XAI_BASE}/stt",
            headers={"Authorization": f"Bearer {key}"},
            data={
                "model": STT_MODEL,
                "format": "true",
                "language": "en",
                "keyterm": ["kilometer", "satellite", "debris", "Starlink"],
            },
            files={"file": (filename, audio, content_type or "application/octet-stream")},
        )
        response.raise_for_status()
        payload = response.json()
    text = payload.get("text") or payload.get("transcript") or ""
    if not str(text).strip():
        raise RuntimeError("Grok STT returned empty text")
    return str(text).strip()


def imagine(prompt: str) -> dict:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is not set")
    labeled = (
        f"Illustration, not a data plot. {prompt}. Dark Earth, amber debris, pale satellites, "
        "cinematic, no fake axis labels or invented statistics."
    )
    client = _client()
    response = client.images.generate(model=IMAGINE_MODEL, prompt=labeled)
    item = response.data[0]
    return {
        "url": getattr(item, "url", None),
        "b64_json": getattr(item, "b64_json", None),
        "label": "Illustration (Grok Imagine). Data is drawn from CelesTrak, not this image.",
    }
