"""Chalk evaluation task and scorers for the junk-band eval (see junk_eval.py).

WARNING: importing this module deploys four functions to Chalk. Run with
    uv run --with chalkcompute --with chalkpy python -m chalk_tools.run_junk_eval
"""
from __future__ import annotations

import json

import chalkcompute

from chalk_tools import junk_eval
from chalk_tools.ask_image import LIGHT_IMAGE, build_image

REV = "2"  # bump to force a new function version when only a helper module changed
ASK_IMAGE = build_image(code_strategy="volume", entrypoint=False)


@chalkcompute.function(image=ASK_IMAGE, tracing=True, cpu="1", memory="2Gi")
def ask_task(question: str) -> str:
    """The same ask_core.answer the live /ask endpoint serves (errors included, as {"error": ...})."""
    from chalk_tools import ask_core
    _ = REV
    with chalkcompute.span("ask.answer"):
        return json.dumps(ask_core.answer(question))


@chalkcompute.function(image=LIGHT_IMAGE, tracing=True)
def junk_band(output: str, kind: str) -> list[chalkcompute.EvaluationScorerResult]:
    """1.0 when a 'where should I put it' answer avoids 750 to 850 km and recommends a shell with lifetime under 25 years.
    Emits nothing for other kinds of question."""
    _ = REV
    r = junk_eval.junk_band(kind, output)
    if r is None:
        return []
    return [chalkcompute.EvaluationScorerResult(score=r["score"], metadata={k: v for k, v in r.items() if k != "score"})]


@chalkcompute.function(image=LIGHT_IMAGE, tracing=True)
def grounded(output: str, question: str) -> float:
    _ = REV
    return junk_eval.grounded(question, output)["score"]


@chalkcompute.function(image=LIGHT_IMAGE, tracing=True)
def guardrails_ok(output: str) -> float:
    _ = REV
    return junk_eval.guardrails(output)["score"]
