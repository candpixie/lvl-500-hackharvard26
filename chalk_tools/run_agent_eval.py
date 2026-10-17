"""Run the real Grok agent (api/agent.py run_agent) on the tool-call cases and score it locally. No Chalk upload.

Mode "direct": CHALK_ASK_URL is unset and CHALK_REMOTE_FUNCTIONS is on, so Grok picks among the deployed Chalk
functions itself (the names the cases expect). Needs XAI_API_KEY in .env.
Run: uv run --with chalkcompute --with chalkpy --with openai --with httpx --with flask python -m chalk_tools.run_agent_eval [--limit N] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

from chalk_tools import agent_scorers as S
from chalk_tools.tool_call_cases import CASES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="agent_eval_results.json")
    a = ap.parse_args()

    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)  # api.agent does not load it; api.main does
    import api.agent as agent
    if not agent.has_xai_key():
        sys.exit("XAI_API_KEY is not set: refusing to score the local fallback as if it were Grok")
    os.environ["CHALK_ASK_URL"] = ""
    os.environ["CHALK_REMOTE_FUNCTIONS"] = "1"

    rows = []
    for c in CASES[: a.limit]:
        try:
            out = agent.run_agent(c["question"], history=c["history"], context=c["context"])
            err = None
        except Exception as exc:  # keep going; a crash is a result
            out, err = {"answer": "", "tool_calls": []}, type(exc).__name__
        calls = [{"name": t.get("name"), "args": t.get("arguments") or {}, "result": t.get("result")} for t in out.get("tool_calls", [])]
        ans = out.get("answer", "") or ""
        results = [t["result"] for t in calls if isinstance(t["result"], dict)]
        tc = S.score_tool_calls(c, calls)
        row = {"id": c["id"], "group": c["group"], "question": c["question"], "error": err, "answer": ans,
               "calls": [{"name": t["name"], "args": t["args"]} for t in calls], "tool": tc,
               "grounding": S.grounding(ans, results, c["question"], c["context"]),
               "guardrails": S.guardrails(ans, results),
               "valid_shape": S.json_valid({"answer": ans, "tool_calls": [{"name": t["name"], "args": t["args"]} for t in calls]})}
        rows.append(row)
        print(c["id"], "tool", round(tc["overall"], 2), "ground", row["grounding"]["score"], "guard", row["guardrails"]["score"],
              [t["name"] for t in calls], file=sys.stderr)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)

    def mean(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 3) if xs else None
    print(f"\n{len(rows)} cases | crashes {sum(bool(r['error']) for r in rows)}")
    for k in ("selection", "args", "valid", "budget", "overall"):
        print(f"tool {k}: {mean(r['tool'][k] for r in rows)}")
    print("grounded:", mean(r["grounding"]["score"] for r in rows), "| guardrails:", mean(r["guardrails"]["score"] for r in rows))
    g = defaultdict(list)
    for r in rows:
        g[r["group"]].append(r["tool"]["overall"])
    for k, v in g.items():
        print(f"  {k}: {mean(v)} ({len(v)})")


if __name__ == "__main__":
    main()
