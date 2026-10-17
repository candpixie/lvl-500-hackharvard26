"""Deploy the ask reasoner to Chalk as an HTTP scaling group, then smoke test it.

    uv run --with chalkcompute --with chalkpy python -m chalk_tools.deploy_ask

Creates one scaling group (name orbit-ask) that serves POST /ask for the team's CHALK_ASK_URL
(docs/chalk-ask-service.md). It requires a Chalk access token (authenticated=True); anyone calling it from outside
Chalk sends `Authorization: Bearer $(chalk token get --expires-in 24h)`. Set authenticated=False below only if the
team accepts a public URL anyone can call.
"""
import json
import sys

import chalkcompute
from chalkcompute import Image, ScalingGroup, StartupProbe

from chalk_tools import core

ROOT = core.ROOT
NAME = "orbit-ask"
PORT = 8080
DATA = {  # local file -> path inside the container; data uses volume mode because "copy" caps files at 32 KiB
    ROOT / "data/out/shells.json": "/app/data/shells.json",
    ROOT / "data/out/close_approaches.json": "/app/data/close_approaches.json",
    ROOT / "data/out/tools/catalog.csv.gz": "/app/data/catalog.csv.gz",
}
CODE = {
    ROOT / "pipeline/orbit_data.py": "/app/pipeline/orbit_data.py",
    ROOT / "pipeline/scoring.py": "/app/pipeline/scoring.py",
    ROOT / "chalk_tools/ask_core.py": "/app/ask_core.py",
    ROOT / "chalk_tools/ask_app.py": "/app/app.py",
}


def build_image():
    img = (Image.debian_slim("3.12").pip_install(["flask", "numpy", "pandas", "chalkcompute"])
           .env({"ASK_PIPELINE": "/app/pipeline", "ASK_DATA": "/app/data", "PYTHONUNBUFFERED": "1"}))
    for src, dst in CODE.items():
        img = img.add_local_file(str(src), dst, strategy="copy")
    for src, dst in DATA.items():
        img = img.add_local_file(str(src), dst, strategy="volume")
    return img.workdir("/app").entrypoint(["python", "/app/app.py"])


def main():
    missing = [str(p) for p in (*CODE, *DATA) if not p.exists()]
    if missing:
        sys.exit(f"missing files: {missing}")
    sg = ScalingGroup(image=build_image(), name=NAME, port=PORT, min_replicas=1, max_replicas=1,
                      authenticated=True, tracing=chalkcompute.TracingPolicy(sample_rate=1.0),
                      startup_probe=StartupProbe.http("/health")).deploy()
    print("web_url:", sg.web_url)
    health = sg.call("/health", method="GET")
    print("health:", health.status, health.text())
    for q in ("Where should I put 1,000 four-meter satellites?", "What's the closest near miss this week?"):
        r = sg.call("/ask", method="POST", json={"question": q})
        body = json.loads(r.text())
        print(r.status, body.get("focus"), body.get("latency_ms"), "ms |", (body.get("answer") or body.get("error"))[:110])


if __name__ == "__main__":
    main()
