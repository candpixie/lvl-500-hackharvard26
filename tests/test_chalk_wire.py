"""Client contract tests. No network, no .env reads, no secrets in assertions."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from api.agent import (
    _context_note,
    _focus_from_calls,
    _input_messages,
    _reasoner,
    _tools,
    ui_events_for,
)
from api.chalk import (
    DEFAULT_TIMEOUT,
    REMOTE_TIMEOUT,
    ask_chalk,
    call_remote,
    normalize_envelope,
    ping,
    redact,
    remote_functions_enabled,
)
from api.main import health


FAKE_TOKEN = "test-token-not-real"


class _Client:
    def __init__(self, timeout, follow_redirects=False):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers, json))
        raise httpx.ConnectError(f"Bearer {FAKE_TOKEN} at https://evil.example/ask?x={FAKE_TOKEN}")

    def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        response = httpx.Response(405, request=httpx.Request("GET", url))
        return response


class ChalkContractTests(unittest.TestCase):
    def test_timeouts_are_five_seconds(self):
        self.assertEqual(DEFAULT_TIMEOUT, 5.0)
        self.assertEqual(REMOTE_TIMEOUT, 5.0)

    def test_redact_drops_urls_and_bearer(self):
        text = redact(f"Bearer {FAKE_TOKEN} https://host/ask?token={FAKE_TOKEN}")
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn("https://", text)

    def test_headers_stay_off_plain_http(self):
        from api.chalk import _headers

        with patch.dict("os.environ", {"CHALK_TOKEN": FAKE_TOKEN, "CHALK_ENV_ID": "spcwce09a241"}, clear=False):
            local = _headers("http://example.com/ask")
            loopback = _headers("http://127.0.0.1:8001/ask")
            secure = _headers("https://chalk.example/ask")
        self.assertNotIn("Authorization", local)
        self.assertNotIn("x-chalk-env-id", local)
        self.assertIn("Authorization", loopback)
        self.assertEqual(secure.get("x-chalk-env-id"), "spcwce09a241")
        self.assertTrue(secure.get("Authorization", "").endswith(FAKE_TOKEN))

    def test_ask_error_does_not_echo_the_token(self):
        with patch.dict("os.environ", {"CHALK_ASK_URL": "https://chalk.example/ask", "CHALK_TOKEN": FAKE_TOKEN}):
            with patch("api.chalk.httpx.Client", _Client):
                result = ask_chalk("where should 1000 satellites go?")
        self.assertTrue(result.get("fallback"))
        self.assertNotIn(FAKE_TOKEN, json.dumps(result))
        self.assertNotIn("https://", result["error"])

    def test_ping_unset_skips_the_network(self):
        with patch.dict("os.environ", {"CHALK_ASK_URL": ""}, clear=False):
            with patch("api.chalk.httpx.Client", side_effect=AssertionError("network")):
                result = ping()
        self.assertEqual(result, {"ok": False, "detail": "unset"})

    def test_ping_treats_405_as_up_and_does_not_post(self):
        client = _Client(2.0)

        class Factory(_Client):
            def __init__(self, timeout, follow_redirects=False):
                super().__init__(timeout, follow_redirects)
                client.calls = self.calls

        with patch.dict("os.environ", {"CHALK_ASK_URL": "https://chalk.example/ask", "CHALK_TOKEN": FAKE_TOKEN}):
            with patch("api.chalk.httpx.Client", Factory):
                result = ping()
        self.assertEqual(result["ok"], True)
        self.assertEqual(client.calls[0][0], "get")
        blob = json.dumps(result)
        self.assertNotIn(FAKE_TOKEN, blob)

    def test_health_reports_probe_not_just_the_env_var(self):
        with patch("api.main.chalk_ping", return_value={"ok": False, "detail": "unset"}):
            body = health()
        self.assertEqual(body["chalk"], False)
        self.assertEqual(body["reasoner"], "local")
        self.assertNotIn("chalk_error", body)

        with patch("api.main.chalk_ping", return_value={"ok": False, "detail": "unreachable"}):
            down = health()
        self.assertEqual(down["chalk_error"], "unreachable")
        self.assertNotIn(FAKE_TOKEN, json.dumps(down))

        with patch("api.main.chalk_ping", return_value={"ok": True, "detail": "ok"}):
            up = health()
        self.assertEqual(up["chalk"], True)
        self.assertEqual(up["reasoner"], "chalk")

    def test_envelope_json_string(self):
        raw = json.dumps({"ok": True, "data": {"total": 3}, "coverage": {}, "caveats": [], "snapshot_id": "abc"})
        parsed = normalize_envelope(raw)
        self.assertEqual(parsed["data"]["total"], 3)
        self.assertNotIn("fallback", parsed)
        failed = normalize_envelope('{"ok": false, "error": {"type": "out_of_range", "message": "no"}}')
        self.assertTrue(failed["fallback"])

    def test_remote_tools_are_opt_in_and_rank_place_stay(self):
        with patch.dict("os.environ", {"CHALK_REMOTE_FUNCTIONS": ""}, clear=False):
            self.assertFalse(remote_functions_enabled())
            names = [tool["name"] for tool in _tools(False, False)]
        self.assertNotIn("shell_crowding", names)
        self.assertIn("rank_shells", names)
        self.assertIn("place_satellites", names)

        with patch.dict("os.environ", {"CHALK_REMOTE_FUNCTIONS": "1"}, clear=False):
            self.assertTrue(remote_functions_enabled())
            names = [tool["name"] for tool in _tools(True, True)]
        for name in ("ask_chalk", "shell_crowding", "objects_near", "close_approaches", "recommend_orbit", "rank_shells", "place_satellites"):
            self.assertIn(name, names)

    def test_remote_kwargs_always_pass_every_argument(self):
        from api.chalk import _remote_kwargs
        self.assertEqual(_remote_kwargs("recommend_orbit", {"inclination_deg": 98}),
                         {"inclination_deg": 98.0, "min_altitude_km": 400.0, "max_altitude_km": 1200.0,
                          "top_n": 5, "inclination_band_deg": 10.0})
        self.assertEqual(_remote_kwargs("objects_near", {"altitude_km": 550, "inclination_deg": 53})["limit"], 10)
        self.assertEqual(_remote_kwargs("close_approaches", {"min_altitude_km": 500, "max_altitude_km": 550, "limit": 3})["limit"], 3)
        with self.assertRaises(ValueError):
            _remote_kwargs("recommend_orbit", {})

    def test_call_remote_uses_from_name_and_parses_json(self):
        seen = {}

        class Handle:
            def remote(self, **kwargs):
                seen["kwargs"] = kwargs
                return json.dumps({
                    "ok": True,
                    "data": {"shell_km": [500, 550], "total": 9},
                    "coverage": {},
                    "caveats": [],
                    "snapshot_id": "snap",
                })

        class RemoteFunction:
            @staticmethod
            def from_name(name, call_timeout=None):
                seen["name"] = name
                seen["timeout"] = call_timeout
                return Handle()

        import sys
        import types

        module = types.ModuleType("chalkcompute")
        module.RemoteFunction = RemoteFunction
        with patch.dict("os.environ", {"CHALK_REMOTE_FUNCTIONS": "1", "CHALK_ENV_ID": "spcwce09a241"}):
            with patch.dict(sys.modules, {"chalkcompute": module}):
                from api import chalk as chalk_mod

                chalk_mod._handles.clear()
                result = call_remote("shell_crowding", {"altitude_km": 525})
        self.assertEqual(seen["name"], "shell_crowding")
        self.assertEqual(seen["timeout"], 5.0)
        self.assertEqual(seen["kwargs"], {"altitude_km": 525.0, "inclination_deg": None})
        self.assertEqual(result["data"]["total"], 9)
        self.assertEqual(result["snapshot_id"], "snap")

    def test_remote_off_does_not_import_the_sdk(self):
        with patch.dict("os.environ", {"CHALK_REMOTE_FUNCTIONS": ""}, clear=False):
            result = call_remote("objects_near", {"altitude_km": 420, "inclination_deg": 51.6})
        self.assertTrue(result["fallback"])
        self.assertEqual(result["error"]["type"], "disabled")

    def test_focus_and_reasoner(self):
        calls = [{
            "name": "shell_crowding",
            "result": {"ok": True, "data": {"shell_km": [800, 850]}},
        }]
        focus = _focus_from_calls(calls)
        self.assertEqual(focus["altitude_km"], 825)
        self.assertEqual(_reasoner(calls), "chalk")
        mixed = calls + [{"name": "rank_shells", "result": []}]
        self.assertEqual(_reasoner(mixed), "local_fallback")

    def test_focus_copies_count_from_rank_tools(self):
        calls = [{
            "name": "ask_chalk",
            "result": {
                "answer": "500 to 550.",
                "focus": {"altitude_km": 525, "inclination_deg": 53},
                "tool_calls": [{
                    "name": "rank_shells",
                    "arguments": {"count": 1, "dims_m": [4, 2, 1], "top": 3},
                    "result": [{"alt_lo": 500, "alt_hi": 550}],
                }],
            },
        }]
        focus = _focus_from_calls(calls)
        self.assertEqual(focus["altitude_km"], 525)
        self.assertEqual(focus["count"], 1)
        self.assertEqual(focus["dims_m"], [4.0, 2.0, 1.0])

    def test_why_focus_does_not_steal_rank_count(self):
        calls = [{
            "name": "ask_chalk",
            "result": {
                "answer": "800 is debris.",
                "focus": {"altitude_km": 825, "inclination_deg": 53},
                "tool_calls": [
                    {"name": "get_shell_crowding", "arguments": {"alt_km": 800}, "result": {"alt_lo": 800, "alt_hi": 850}},
                    {"name": "rank_shells", "arguments": {"count": 1, "dims_m": [4, 2, 1], "top": 1}, "result": []},
                ],
            },
        }]
        focus = _focus_from_calls(calls)
        self.assertEqual(focus["altitude_km"], 825)
        self.assertNotIn("count", focus)

    def test_fallback_rank_fills_count_onto_chalk_focus(self):
        calls = [
            {
                "name": "ask_chalk",
                "result": {
                    "answer": "500 to 550.",
                    "focus": {"altitude_km": 525, "inclination_deg": 53},
                    "tool_calls": [],
                },
            },
            {
                "name": "rank_shells",
                "arguments": {"count": 1, "dims_m": [4, 2, 1]},
                "result": [{"alt_lo": 500, "alt_hi": 550}],
            },
        ]
        focus = _focus_from_calls(calls)
        self.assertEqual(focus["altitude_km"], 525)
        self.assertEqual(focus["count"], 1)

    def test_context_drops_unknown_keys(self):
        note = _context_note({
            "altitude_km": 550,
            "inclination_deg": 53,
            "selected_norad": 25544,
            "CHALK_TOKEN": FAKE_TOKEN,
            "api_key": "sk-should-not-appear",
        })
        self.assertIn("altitude_km=550", note)
        self.assertIn("selected_norad=25544", note)
        self.assertNotIn(FAKE_TOKEN, note)
        self.assertNotIn("sk-", note)

    def test_history_is_not_stored(self):
        first = _input_messages("sys", "q1", [{"role": "user", "content": "earlier"}], {"altitude_km": 500})
        second = _input_messages("sys", "q2", None, None)
        self.assertEqual(len(second), 2)
        self.assertEqual(first[1]["content"], "earlier")
        self.assertIn("Context: altitude_km=500", first[-1]["content"])

    def test_run_agent_adds_focus_orbit_without_a_session(self):
        payload = {
            "answer": "500 to 550 is less crowded.",
            "focus": {"altitude_km": 525, "inclination_deg": 53},
            "tool_calls": [],
            "reasoner": "local",
        }
        with patch("api.agent.ask", return_value=payload) as ask:
            from agent import run_agent

            out = run_agent("where?", history=[{"question": "hi", "answer": "ok"}], context={"altitude_km": 800})
        ask.assert_called_once()
        self.assertEqual(ask.call_args.args[0], "where?")
        self.assertEqual(out["ui_events"], [{"type": "focusOrbit", "altitude_km": 525, "inclination_deg": 53}])
        self.assertEqual(ui_events_for({"focus": None}), [])
        self.assertEqual(out["answer"], payload["answer"])


if __name__ == "__main__":
    unittest.main()
