"""Flask wrapper that serves ask_core on a Chalk scaling group.  POST /ask {question} -> {answer, focus, tool_calls, note}.

Contract: docs/chalk-ask-service.md. A question these resolvers cannot answer returns HTTP 422 with {"error": ...}, which
makes the team's Grok client fall back to its local tools. GET /health reports the data snapshot. GET /ask is 405,
which the client's health probe counts as up.
Local:   uv run --with flask python chalk_tools/ask_app.py     (port 8080, or PORT)
Deploy:  uv run --with chalkcompute --with chalkpy python -m chalk_tools.deploy_ask
"""
import logging
import os
import time
from contextlib import contextmanager

from flask import Flask, jsonify, request

try:  # in the Chalk image this file sits next to ask_core.py
    import ask_core as core
except ImportError:
    from chalk_tools import ask_core as core

_init_error = None
_exporter_kind = None
_export_stats = {"batches_ok": 0, "batches_failed": 0, "spans": 0}
_otel_messages: list = []  # recent OpenTelemetry log lines, shown on /health so export failures are visible


class _Capture(logging.Handler):
    def emit(self, record):
        _otel_messages.append(f"{record.levelname} {record.name}: {record.getMessage()}"[:300])
        del _otel_messages[:-6]


logging.getLogger("opentelemetry").addHandler(_Capture())
logging.getLogger("opentelemetry").setLevel(logging.DEBUG)


def _collector_speaks_grpc(endpoint: str) -> bool:
    """Chalk gives no protocol hint, and its collector port is not the standard HTTP one, so ask the port."""
    try:
        import grpc
        target = endpoint.split("://", 1)[-1].rstrip("/")
        with grpc.insecure_channel(target) as channel:
            grpc.channel_ready_future(channel).result(timeout=3)
        return True
    except Exception:
        return False


def _init_tracing():
    """Send spans to the collector Chalk points this container at (OTEL_EXPORTER_OTLP_ENDPOINT). Never blocks serving."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON
        global _exporter_kind
        if _collector_speaks_grpc(endpoint) if not os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") else os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL").startswith("grpc"):
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            _exporter_kind = "grpc"
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            _exporter_kind = "http"
            exporter = OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
        env_id = os.getenv("CHALK_ENVIRONMENT_ID") or os.getenv("CHALK_ENVIRONMENT") or "spcwce09a241"
        provider = TracerProvider(sampler=ALWAYS_ON, resource=Resource.create({
            "service.name": "orbit-ask", "chalk.component": "compute-scaling-group",
            "chalk.environment_id": env_id, "chalk_environment_id": env_id,
            "chalk.team_id": os.getenv("CHALK_TEAM_ID") or "cmvbyon5y011y010nkd7dncrz"}))
        from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

        class CountingExporter(SpanExporter):
            """Wraps the real exporter and counts results so /health can show whether exports reach the collector."""
            def export(self, spans):
                result = exporter.export(spans)
                key = "batches_ok" if result == SpanExportResult.SUCCESS else "batches_failed"
                _export_stats[key] += 1
                _export_stats["spans"] += len(spans)
                return result

            def shutdown(self):
                return exporter.shutdown()

            def force_flush(self, timeout_millis=30000):
                return exporter.force_flush(timeout_millis)

        provider.add_span_processor(BatchSpanProcessor(CountingExporter(), schedule_delay_millis=1000))
        trace.set_tracer_provider(provider)
        return trace.get_tracer("orbit-ask")
    except Exception as exc:
        global _init_error
        _init_error = f"{type(exc).__name__}: {exc}"[:200]
        return None


_tracer = _init_tracing()


@contextmanager
def span(name, **attrs):
    """A span when tracing is set up; otherwise a no-op (local runs and tests)."""
    if _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            s.set_attribute(k, v)
        yield

MAX_QUESTION_CHARS = 600
app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True, "snapshot": core.resolvers().snapshot,
            "tracing": {"enabled": _tracer is not None, "exporter": _exporter_kind, "init_error": _init_error, "otel_log": list(_otel_messages), "export_stats": dict(_export_stats),
                        "env_names": sorted(k for k in os.environ if k.startswith(("CHALK_", "OTEL_")) and not any(w in k for w in ("TOKEN", "SECRET", "KEY"))),
                        **{k.lower(): os.getenv(k) for k in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_TRACES_SAMPLER_ARG", "OTEL_RESOURCE_ATTRIBUTES",
                           "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_TRACES_SAMPLER", "OTEL_SERVICE_NAME")}}}


@app.post("/ask")
def ask():
    body = request.get_json(silent=True)
    question = body.get("question") if isinstance(body, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        return jsonify({"error": f"question (a string up to {MAX_QUESTION_CHARS} characters) is required"}), 400
    started = time.perf_counter()
    try:
        with span("ask.answer", **{"question.chars": len(question)}):
            result = core.answer(question.strip())
    except ValueError as exc:  # for example an altitude outside 300 to 2,000 km
        return jsonify({"error": str(exc)}), 422
    except Exception:
        app.logger.exception("ask failed")
        return jsonify({"error": "internal error"}), 500
    if "error" in result:
        return jsonify(result), 422
    result["source"] = "chalk"
    with span("ask.respond", **{"answer.chars": len(result.get("answer", "")), "tool_calls.count": len(result.get("tool_calls", []))}):
        pass
    result["snapshot"] = core.resolvers().snapshot
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), threaded=True)
