"""Call the Chalk reasoner. Grok must use this before any local fallback tools.

Teammates implement POST CHALK_ASK_URL with the body in docs/chalk-ask-service.md.
That HTTP contract stays {question} -> {answer, focus, tool_calls}. Their deployed
functions (shell_crowding, objects_near, close_approaches) use a different
envelope, {ok, data, coverage, caveats, snapshot_id}, and are optional.

Set CHALK_ASK_URL in .env to turn the HTTP path on. If unset, /ask uses local
tools only. Never import chalk_tools.functions: that module deploys on import.
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any
from urllib.parse import urlparse

import httpx

# Voice budget from the split: Chalk 5s, then local place / rank / SOCRATES.
DEFAULT_TIMEOUT = 5.0
PING_TIMEOUT = 2.0
REMOTE_TIMEOUT = 5.0
REMOTE_FUNCTIONS = ("shell_crowding", "objects_near", "close_approaches", "recommend_orbit")

_SECRET = re.compile(
    r"(?i)(bearer\s+\S+|api[_-]?key|token|secret|authorization|sk-|xai-|eyJ[A-Za-z0-9_-]{8,})"
)
_URL = re.compile(r"https?://\S+")
_handles: dict[str, Any] = {}
_handle_lock = threading.Lock()


def ask_url() -> str:
    return (os.getenv("CHALK_ASK_URL") or "").strip().rstrip("/")


def enabled() -> bool:
    return bool(ask_url())


def remote_functions_enabled() -> bool:
    flag = (os.getenv("CHALK_REMOTE_FUNCTIONS") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _token_allowed(url: str) -> bool:
    """Send the bearer only to https, or to http on localhost. Never to a bare http host."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}


def _headers(url: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if not _token_allowed(url):
        return headers
    token = os.getenv("CHALK_TOKEN") or os.getenv("CHALK_CLIENT_SECRET") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    env_id = (os.getenv("CHALK_ENV_ID") or "").strip()
    if env_id:
        headers["x-chalk-env-id"] = env_id
    return headers


def redact(raw: str) -> str:
    """Short error text with URLs and credential-shaped strings removed."""
    text = _URL.sub("[url]", raw or "")
    text = text.replace("\n", " ").strip()
    if not text or _SECRET.search(text):
        return "tool failed"
    return text[:160]


def _public_detail(prefix: str, raw: str = "") -> str:
    text = redact(raw)
    if text == "tool failed":
        return prefix
    return f"{prefix}: {text}"


def ask_chalk(question: str) -> dict[str, Any]:
    """POST the user question to Chalk. Returns their JSON or {error: ...}."""
    url = ask_url()
    if not url:
        return {"error": "CHALK_ASK_URL is not set", "fallback": True}
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=False) as client:
            response = client.post(url, headers=_headers(url), json={"question": question})
    except httpx.HTTPError as exc:
        return {"error": _public_detail("Chalk unreachable", str(exc)), "fallback": True}
    if response.status_code >= 400:
        return {"error": f"Chalk HTTP {response.status_code}", "fallback": True}
    try:
        payload = response.json()
    except ValueError:
        return {"error": "Chalk returned non-JSON", "fallback": True}
    if not isinstance(payload, dict):
        return {"error": "Chalk JSON must be an object", "fallback": True}
    if payload.get("error"):
        payload["fallback"] = True
        return payload
    return payload


def ping() -> dict[str, Any]:
    """Reach the Chalk ask host. Does not send a question and does not return response bodies.

    GET is the probe so a POST-only /ask is not executed. 405/400/415 still count as up.
    """
    url = ask_url()
    if not url:
        return {"ok": False, "detail": "unset"}
    try:
        with httpx.Client(timeout=PING_TIMEOUT, follow_redirects=False) as client:
            response = client.get(url, headers=_headers(url))
    except httpx.HTTPError:
        return {"ok": False, "detail": "unreachable"}
    status = response.status_code
    if status in {401, 403}:
        return {"ok": False, "detail": "auth"}
    if status == 404:
        return {"ok": False, "detail": "not_found"}
    if status >= 500:
        return {"ok": False, "detail": "http_5xx"}
    return {"ok": True, "detail": "ok"}


def chalk_ok(result: Any) -> bool:
    return isinstance(result, dict) and not result.get("error") and not result.get("fallback")


def _bind_environment() -> None:
    """Point the Chalk SDK at CHALK_ENV_ID without writing .env. Do not override an SDK var already set."""
    env_id = (os.getenv("CHALK_ENV_ID") or "").strip()
    if env_id and not (os.getenv("CHALK_ENVIRONMENT_ID") or "").strip():
        os.environ["CHALK_ENVIRONMENT_ID"] = env_id


def normalize_envelope(raw: Any) -> dict[str, Any]:
    """Accept the deployed functions' JSON string or object. Failures are fallbacks."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {
                "ok": False,
                "error": {"type": "bad_json", "message": "Chalk function returned non-JSON"},
                "fallback": True,
            }
    if not isinstance(raw, dict):
        return {
            "ok": False,
            "error": {"type": "bad_envelope", "message": "Chalk function returned a non-object"},
            "fallback": True,
        }
    if raw.get("ok") is False or raw.get("error"):
        raw = dict(raw)
        raw["fallback"] = True
    return raw


def _fallback(kind: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"type": kind, "message": message}, "fallback": True}


def _limit(args: dict) -> int:
    return 10 if args.get("limit") in (None, "") else int(float(args["limit"]))


def _remote_kwargs(name: str, args: dict) -> dict[str, Any]:
    def required(key: str) -> float:
        if args.get(key) in (None, ""):
            raise ValueError(f"{key} is required")
        return float(args[key])

    if name == "shell_crowding":
        # RemoteFunction.from_name does not apply default arguments, so every argument is always passed.
        inc = args.get("inclination_deg")
        return {"altitude_km": required("altitude_km"),
                "inclination_deg": None if inc in (None, "") else float(inc)}
    if name == "objects_near":
        kwargs = {
            "altitude_km": required("altitude_km"),
            "inclination_deg": required("inclination_deg"),
            "limit": _limit(args),
        }
        return kwargs
    if name == "close_approaches":
        kwargs = {
            "min_altitude_km": required("min_altitude_km"),
            "max_altitude_km": required("max_altitude_km"),
            "limit": _limit(args),
        }
        return kwargs
    if name == "recommend_orbit":
        def num(key: str, default: float) -> float:
            return default if args.get(key) in (None, "") else float(args[key])

        return {
            "inclination_deg": required("inclination_deg"),
            "min_altitude_km": num("min_altitude_km", 400.0),
            "max_altitude_km": num("max_altitude_km", 1200.0),
            "top_n": int(num("top_n", 5)),
            "inclination_band_deg": num("inclination_band_deg", 10.0),
        }
    raise ValueError(f"unknown tool {name}")


def _remote_handle(name: str):
    with _handle_lock:
        cached = _handles.get(name)
        if cached is not None:
            return cached
    import chalkcompute

    _bind_environment()
    handle = chalkcompute.RemoteFunction.from_name(name, call_timeout=REMOTE_TIMEOUT)
    with _handle_lock:
        _handles[name] = handle
        return handle


def call_remote(name: str, args: dict | None) -> dict[str, Any]:
    """Call one deployed Chalk function by name. Local rank/place stay in api.agent until recommend_orbit exists."""
    if name not in REMOTE_FUNCTIONS:
        return _fallback("unknown_tool", "That Chalk function is not wired.")
    if not remote_functions_enabled():
        return _fallback("disabled", "CHALK_REMOTE_FUNCTIONS is off.")
    try:
        kwargs = _remote_kwargs(name, args or {})
    except (TypeError, ValueError):
        return _fallback("invalid_argument", "Chalk function arguments were not numbers.")
    try:
        handle = _remote_handle(name)
        raw = handle.remote(**kwargs)
    except ImportError:
        return _fallback("missing_sdk", "chalkcompute is not installed.")
    except Exception as exc:
        return _fallback(type(exc).__name__, _public_detail("Chalk function failed", type(exc).__name__))
    return normalize_envelope(raw)
