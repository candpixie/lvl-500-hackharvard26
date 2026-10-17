"""Health and manifest helpers for B's server to mount as /api/health and /api/manifest.

check_chalk() makes one cheap call to each deployed Chalk function and reports ok/down with latency, so the
pre-demo checklist can see a problem before the audience does. Needs chalkcompute and a Chalk login to run;
importing this module needs neither.
"""
from __future__ import annotations

import json
import time

from chalk_tools import core

PROBES = {"shell_crowding": (550.0, None), "objects_near": (420.0, 51.6, 1),
          "close_approaches": (400.0, 600.0, 1), "recommend_orbit": (53.0, 400.0, 1200.0, 1, 10.0)}


def manifest() -> dict:
    return json.loads((core.ROOT / "data/out/manifest.json").read_text())


def check_chalk(timeout: float = 5.0) -> dict:
    """{"ok": bool, "functions": {name: {"ok": bool, "ms": float|None, "error": str|None}}, "snapshot_id": str|None}"""
    out, snapshot = {}, None
    try:
        import chalkcompute
    except ImportError as exc:
        return {"ok": False, "functions": {}, "snapshot_id": None, "error": f"chalkcompute not installed: {exc}"}
    for name, args in PROBES.items():
        t0 = time.perf_counter()
        try:
            fn = chalkcompute.RemoteFunction.from_name(name, call_timeout=timeout)
            res = json.loads(fn.remote(*args))
            snapshot = snapshot or res.get("snapshot_id")
            out[name] = {"ok": bool(res.get("ok")), "ms": round((time.perf_counter() - t0) * 1000, 1), "error": None}
        except Exception as exc:
            out[name] = {"ok": False, "ms": None, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"ok": all(v["ok"] for v in out.values()), "functions": out, "snapshot_id": snapshot}
