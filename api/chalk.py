"""Call the Chalk reasoner. Grok must use this before any local fallback tools.

Teammates implement POST CHALK_ASK_URL with the body in docs/chalk-contract.md.
Set CHALK_ASK_URL in .env to turn this on. If unset, /ask uses local tools only.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_TIMEOUT = 45.0


def ask_url() -> str:
    return (os.getenv("CHALK_ASK_URL") or "").rstrip("/")


def enabled() -> bool:
    return bool(ask_url())


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("CHALK_TOKEN") or os.getenv("CHALK_CLIENT_SECRET") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    env_id = os.getenv("CHALK_ENV_ID") or ""
    if env_id:
        headers["x-chalk-env-id"] = env_id
    return headers


def ask_chalk(question: str) -> dict[str, Any]:
    """POST the user question to Chalk. Returns their JSON or {error: ...}."""
    url = ask_url()
    if not url:
        return {"error": "CHALK_ASK_URL is not set", "fallback": True}
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.post(url, headers=_headers(), json={"question": question})
    except httpx.HTTPError as exc:
        return {"error": f"Chalk unreachable: {exc}", "fallback": True}
    if response.status_code >= 400:
        return {
            "error": f"Chalk HTTP {response.status_code}: {response.text[:400]}",
            "fallback": True,
        }
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


def chalk_ok(result: Any) -> bool:
    return isinstance(result, dict) and not result.get("error") and not result.get("fallback")
