"""Create and run the junk-band eval on Chalk and print N/M.

    uv run --with chalkcompute --with chalkpy python -m chalk_tools.run_junk_eval
"""
import json
import sys

import chalkcompute

from chalk_tools import junk_eval
from chalk_tools.junk_eval_functions import ask_task, grounded, guardrails_ok, junk_band

NAME = "ask-junk-band"


def main():
    rows = junk_eval.build_rows()
    dataset = chalkcompute.DatasetClient().upload(NAME, rows)
    scorers = [junk_band, grounded, guardrails_ok]
    evaluation = chalkcompute.Evaluation.create(NAME, dataset=dataset, task=ask_task, scorers=scorers,
                                                metadata={"task": "ask_core.answer, same as the live /ask endpoint"})
    run = evaluation.run(metadata={"rows": len(rows)}).wait()
    print("run", run.id, run.status, file=sys.stderr)
    df = chalkcompute.DatasetClient().read(run.result_dataset).to_pandas()
    cols = [c for c in df.columns if c.startswith("scorer_") and not c.endswith("_error") and not c.endswith("_metadata")]
    print("columns:", [c for c in df.columns if not c.startswith("__chalk__")])
    print("task errors:", int(df.output_error.notna().sum()), "| answered:", int(df.output.map(lambda o: "answer" in json.loads(o)).sum()), "/", len(df))
    for name, sc in zip(("junk_band", "grounded", "guardrails_ok"), evaluation.scorers):
        col = f"scorer_{sc.id}"
        if col not in df.columns:
            print(name, "-> column", col, "not found; have", cols)
            continue
        s = df[col].dropna()
        print(f"{name}: {int(round(s.sum()))}/{len(s)} scored rows pass | scorer errors: {int(df[col + '_error'].notna().sum()) if col + '_error' in df else 'n/a'}")
    print("evaluation id:", evaluation.id, "| run id:", run.id)


if __name__ == "__main__":
    main()
