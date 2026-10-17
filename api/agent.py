"""Grok is the front door (STT, TTS, Imagine). Chalk does reasoning; local tools are fallback."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from openai import OpenAI

from api.chalk import ask_chalk, chalk_ok, enabled as chalk_enabled
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


def _tools() -> list[dict]:
    if chalk_enabled():
        return [CHALK_TOOL, *LOCAL_TOOLS]
    return list(LOCAL_TOOLS)


def _run_tool(name: str, args: dict) -> Any:
    if name == "ask_chalk":
        return ask_chalk(str(args.get("question") or ""))
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
    return rank_focus or place_focus or other


def _reasoner(tool_calls: list[dict]) -> str:
    chalk_calls = [c for c in tool_calls if c["name"] == "ask_chalk"]
    local_calls = [c for c in tool_calls if c["name"] != "ask_chalk"]
    if chalk_calls and chalk_ok(chalk_calls[-1]["result"]) and not local_calls:
        return "chalk"
    if chalk_calls and local_calls:
        return "local_fallback"
    if chalk_calls:
        return "local_fallback"
    return "local"


def ask(question: str) -> dict:
    client = _client()
    tools = _tools()
    use_chalk = chalk_enabled()
    tool_calls: list[dict] = []
    first_choice: Any = {"type": "function", "name": "ask_chalk"} if use_chalk else "auto"
    response = client.responses.create(
        model=ASK_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_CHALK if use_chalk else SYSTEM_LOCAL},
            {"role": "user", "content": question},
        ],
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
                result = {"error": str(exc), "fallback": item.name == "ask_chalk"}
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
