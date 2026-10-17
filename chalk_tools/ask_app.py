"""Flask wrapper that serves ask_core on a Chalk scaling group.  POST /ask {question} -> {answer, focus, tool_calls, note}.

Contract: docs/chalk-contract.md. A question these resolvers cannot answer returns HTTP 422 with {"error": ...}, which
makes the team's Grok client fall back to its local tools. GET /health reports the data snapshot. GET /ask is 405,
which the client's health probe counts as up.
Local:   uv run --with flask python chalk_tools/ask_app.py     (port 8080, or PORT)
Deploy:  uv run --with chalkcompute --with chalkpy python -m chalk_tools.deploy_ask
"""
import os
import time
from contextlib import contextmanager

from flask import Flask, jsonify, request

try:  # in the Chalk image this file sits next to ask_core.py
    import ask_core as core
except ImportError:
    from chalk_tools import ask_core as core

try:
    import chalkcompute
    span = chalkcompute.span
except Exception:  # local runs and tests have no tracing
    @contextmanager
    def span(name):
        yield

MAX_QUESTION_CHARS = 600
app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True, "snapshot": core.resolvers().snapshot}


@app.post("/ask")
def ask():
    body = request.get_json(silent=True)
    question = body.get("question") if isinstance(body, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        return jsonify({"error": f"question (a string up to {MAX_QUESTION_CHARS} characters) is required"}), 400
    started = time.perf_counter()
    try:
        with span("ask.answer"):
            result = core.answer(question.strip())
    except ValueError as exc:  # for example an altitude outside 300 to 2,000 km
        return jsonify({"error": str(exc)}), 422
    except Exception:
        app.logger.exception("ask failed")
        return jsonify({"error": "internal error"}), 500
    if "error" in result:
        return jsonify(result), 422
    result["source"] = "chalk"
    result["snapshot"] = core.resolvers().snapshot
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), threaded=True)
