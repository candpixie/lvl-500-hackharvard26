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


def _mission_from_args(args: Any) -> dict:
    out: dict = {}
    if not isinstance(args, dict):
        return out
    if args.get("count") is not None:
        try:
            count = int(args["count"])
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            out["count"] = count
    dims = args.get("dims_m")
    if isinstance(dims, (list, tuple)) and dims:
        try:
            out["dims_m"] = [float(x) for x in dims]
        except (TypeError, ValueError):
            pass
    return out


def _mission_from_calls(tool_calls: list) -> dict:
    """Count/size from rank/place only when that is the first tool, not a why-style extra rank."""
    if not tool_calls or not isinstance(tool_calls[0], dict):
        return {}
    first = tool_calls[0]
    if first.get("name") in {"rank_shells", "place_satellites"}:
        return _mission_from_args(first.get("arguments"))
    return {}


def _attach_mission(focus: dict | None, *missions: dict) -> dict | None:
    if not focus:
        return None
    out = dict(focus)
    for mission in missions:
        for key, value in mission.items():
            if key not in out and value is not None:
                out[key] = value
    return out


def _fill_mission(focus: dict | None, tool_calls: list[dict]) -> dict | None:
    """If Chalk omitted count, copy it from a rank/place call Grok made in the same turn."""
    if not focus or focus.get("count") is not None:
        return focus
    for call in tool_calls:
        if call.get("name") in {"rank_shells", "place_satellites"}:
            return _attach_mission(focus, _mission_from_args(call.get("arguments")))
    return focus


def _focus_from_calls(tool_calls: list[dict]) -> dict | None:
    chalk_focus = None
    rank_focus = None
    place_focus = None
    other = None
    for call in tool_calls:
        name, result = call["name"], call["result"]
        args = call.get("arguments") or {}
        if name == "ask_chalk" and chalk_ok(result):
            raw = result.get("focus")
            nested = result.get("tool_calls") or []
            nested_mission = _mission_from_calls(nested) if isinstance(nested, list) else {}
            raw_mission = _mission_from_args(raw)
            if isinstance(raw, dict) and raw.get("altitude_km") is not None:
                chalk_focus = _attach_mission(
                    {
                        "altitude_km": raw["altitude_km"],
                        "inclination_deg": raw.get("inclination_deg", DEFAULT_INC_DEG),
                    },
                    raw_mission,
                    nested_mission,
                )
            elif isinstance(nested, list):
                found = _focus_from_calls(nested)
                if found:
                    chalk_focus = _attach_mission(found, nested_mission)
        if name == "rank_shells" and isinstance(result, list):
            rank_focus = _attach_mission(focus_from_rank(result), _mission_from_args(args)) or rank_focus
        elif name == "place_satellites" and isinstance(result, dict) and "alt_km" in result:
            place_focus = _attach_mission(focus_from_place(result), _mission_from_args(args))
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
    return _fill_mission(chalk_focus or rank_focus or place_focus or other, tool_calls)


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


def ui_events_for(result: dict) -> list[dict]:
    focus = result.get("focus") if isinstance(result, dict) else None
    if not isinstance(focus, dict) or focus.get("altitude_km") is None:
        return []
    event = {"type": "focusOrbit", "altitude_km": focus["altitude_km"]}
    if focus.get("inclination_deg") is not None:
        event["inclination_deg"] = focus["inclination_deg"]
    return [event]


def ask(question: str, history: list | None = None, context: dict | None = None) -> dict:
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
    return {
        "answer": answer,
        "focus": _focus_from_calls(tool_calls),
        "tool_calls": [
            {"name": c["name"], "arguments": c["arguments"], "result": c["result"]}
            for c in tool_calls
        ],
        "reasoner": _reasoner(tool_calls),
    }


def run_agent(question: str, history: list | None = None, context: dict | None = None) -> dict:
    """Eval entrypoint. Same loop as ask(). history and context are not stored.

    Returns the /ask fields plus ui_events derived from focus.
    """
    result = ask(question, history=history, context=context)
    return {**result, "ui_events": ui_events_for(result)}


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
