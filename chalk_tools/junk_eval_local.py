"""Local dry run of the junk-band eval (same functions the Chalk run uses).   uv run python -m chalk_tools.junk_eval_local"""
import json
from collections import Counter, defaultdict

from chalk_tools import ask_core, junk_eval


def main():
    rows = junk_eval.build_rows()
    per = defaultdict(list)
    fails = []
    for r in rows:
        out = json.dumps(ask_core.answer(r["question"]))
        jb = junk_eval.junk_band(r["kind"], out)
        g = junk_eval.grounded(r["question"], out)
        gr = junk_eval.guardrails(out)
        per["grounded"].append(g["score"])
        per["guardrails"].append(gr["score"])
        if jb is not None:
            per["junk_band"].append(jb["score"])
            if not jb["score"]:
                fails.append((r["question"], jb))
        if g["score"] == 0 or gr["score"] == 0:
            fails.append((r["question"], {"grounded": g, "guardrails": gr}))
    print(f"{len(rows)} rows:", dict(Counter(r["kind"] for r in rows)))
    for k, v in per.items():
        print(f"{k}: {int(sum(v))}/{len(v)}")
    for q, d in fails[:12]:
        print("FAIL", q, d)


if __name__ == "__main__":
    main()
