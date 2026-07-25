# packages/observability

Structured JSON logging, real OpenTelemetry tracing, Prometheus
metrics, and error reporting - the shared cross-cutting infrastructure
every service can adopt without pulling in FastAPI or each other. See
`docs/adr/0019-observability.md`.

## Modules

| Module | What it does |
|---|---|
| `context.py` | `correlation_id`/`user_id`/`project_id` contextvars - request-scoped, no threading them through every function call |
| `logging.py` | `configure_logging()`/`get_logger()` - one JSON line per log record to stdout, correlation-tagged via a `logging.Filter` |
| `tracing.py` | `configure_tracing()`/`get_tracer()`/`traced_span()` - real OpenTelemetry SDK, `ConsoleSpanExporter` default (needs no collector), `OTLPSpanExporter` available for a real one |
| `metrics.py` | `prometheus_client` Counters/Histograms + `render_metrics()` - real exposition-format text from real counter state |
| `errors.py` | `IErrorReporter` + `LoggingErrorReporter` (default) + `SentryErrorReporter` (real `sentry-sdk` usage, needs a real DSN) |

## Usage

```python
from observability import get_logger, traced_span, context

logger = get_logger(__name__)

def do_something(project_id: str) -> None:
    with traced_span("do_something", project_id=project_id):
        logger.info("doing_something", extra={"project_id": project_id})
```

Every `logger.info(...)`/`.warning(...)`/`.exception(...)` call is an
ordinary stdlib `logging.Logger` call - no new API to learn - but is
JSON-formatted and correlation-tagged once `configure_logging()` has run
(`apps/api/src/api/main.py` does this at import time).

## Wired into

- `apps/api`: `ObservabilityMiddleware` (correlation id, request
  logging, tracing span, request metrics per HTTP request), a global
  `Exception` handler (`IErrorReporter.capture_exception`, never leaks
  a traceback to the client), `GET /metrics`.
- `services/render-orchestrator`: `ProjectLifecycle._publish()` (every
  lifecycle transition already funnels through this one method - a
  structured log line was added there, not sprinkled into all nine
  public methods separately); `_run_generation` wraps
  `GenerationPipeline.generate_plan()` in a span and a duration
  histogram; `GenerationPipeline.generate_shot()` logs per-attempt
  success/failure; `TemporalProjectOrchestrator._run_update` logs both
  the expected-business-rejection and genuinely-unexpected-failure
  paths.

## Status (Phase 8 WP1)

Implemented and tested (`tests/test_observability.py`,
`tests/test_api_observability.py`) - all four modules genuinely
executed, not just structurally validated: real captured OpenTelemetry
spans (the SDK's own `InMemorySpanExporter`), real Prometheus counter
state verified against real HTTP traffic, real JSON log lines with
correlation ids threaded through a real request. `OTLPSpanExporter`/
`SentryErrorReporter` are real, correct code paths genuinely unverified
against a live collector/Sentry project - none reachable in this
sandbox.
