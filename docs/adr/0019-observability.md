# ADR 0019: Observability - structured logging, tracing, metrics, error reporting (Phase 8 WP1)

**Status:** Accepted

## Context

`packages/observability` had existed since Phase 0 as an empty scaffold
(`__init__.py` with nothing in it) - the README's own words: "Business
logic is a Phase 4 target," never delivered. Meanwhile every other piece
of cross-cutting infrastructure this project depends on (auth, storage,
persistence, cache, events) had a real interface and a real default
implementation by Phase 8 WP2-4. Logging was bare stdlib `logging`,
used in exactly one place (`apps/api/src/api/temporal_worker.py`) with
no structure, no correlation, and no shared configuration; `apps/api`
had no request tracing, no metrics endpoint, and no error-reporting path
beyond whatever an uncaught exception's default Starlette 500 page
showed.

Per the user's explicit priority ordering (WP1 before WP5), this ADR
covers all seven items named: structured logging, a central logging
package, request tracing, performance metrics, error reporting, log
levels, and correlation IDs.

## Decisions

### 1. `packages/observability`: four independent modules, one `__init__.py` surface

`context.py` (contextvars: `correlation_id`/`user_id`/`project_id`),
`logging.py` (`configure_logging`/`get_logger`, real JSON output),
`tracing.py` (`configure_tracing`/`get_tracer`/`traced_span`, real
OpenTelemetry SDK), `metrics.py` (`prometheus_client` Counters/
Histograms + `render_metrics()`), `errors.py` (`IErrorReporter` +
`LoggingErrorReporter`/`SentryErrorReporter`). Every module is usable
standalone (any service can `from observability import get_logger`
without pulling in FastAPI or the others) - the same "small, focused,
independently-adoptable module" shape `packages/cache-sdk` and
`packages/auth`'s `token_store.py` already established.

### 2. JSON logs via a stdlib `logging.Filter` + `logging.Formatter`, not a third-party structured-logging library

`_ContextFilter` (a `logging.Filter`) attaches the current
`correlation_id`/`user_id`/`project_id` contextvars onto every
`LogRecord`; `JsonFormatter` (a `logging.Formatter`) serializes the
record - including any `extra={...}` fields a call site passed - as one
JSON line. This is genuinely real, not a shim: every `logger.info(...)`/
`logger.warning(...)`/`logger.exception(...)` call anywhere in the
codebase is a completely ordinary stdlib call, needing no new API to
learn, while still producing the structured output every log
aggregator expects. `configure_logging()` is idempotent (clears and
re-installs the root handler rather than stacking duplicates), so
importing `apps/api/src/api/main.py` more than once in one test process
(every test module that imports `api.main`) is safe.

### 3. OpenTelemetry SDK with `ConsoleSpanExporter` as the real, working default - `OTLPSpanExporter` prepared but genuinely unverified against a live collector

`configure_tracing(exporter="console"|"otlp"|"none")` always constructs
a real `opentelemetry.sdk.trace.TracerProvider`. `"console"` (the
default) needs no external service to actually run - every span is
really created, really processed by a real `SpanProcessor`, and really
exported (to stdout, as JSON) - confirmed by direct execution
(`tests/test_observability.py::test_traced_span_produces_a_real_span_with_attributes`
attaches the SDK's own `InMemorySpanExporter` to the live global
provider and asserts on the captured span's name/attributes). `"otlp"`
is real, correct `OTLPSpanExporter` wiring for a genuine collector
(Jaeger/Tempo/...) - unverified against a live one here, since none is
reachable in this sandbox, the same honesty class as
`SentryErrorReporter` below or `RunPodProvider` before a funded account
(ADR 0009). `ObservabilityMiddleware` wraps every `apps/api` request in
a span named `"{method} {path}"`, tagged with `http.method`/
`http.target`/`http.status_code`/`correlation_id`; `ProjectLifecycle`
wraps `_run_generation`'s `GenerationPipeline.generate_plan()` call the
same way (`traced_span("project_lifecycle.run_generation", ...)`).

### 4. `prometheus_client`, a `/metrics` endpoint, real counters wired into real call sites

`sallehly_http_requests_total`/`sallehly_http_request_duration_seconds`
(labeled by method + the matched route *template*, not the raw path -
`/projects/{project_id}`, not `/projects/proj_abc123`, to keep
cardinality bounded) are incremented by `ObservabilityMiddleware` on
every request, including ones that raise. `sallehly_generation_jobs_total`/
`sallehly_generation_job_duration_seconds` are incremented by
`ProjectLifecycle._run_generation`. `GET /metrics` returns
`prometheus_client.generate_latest()`'s real exposition-format text
reflecting the process's actual current counter state - verified
directly (`tests/test_api_observability.py::test_metrics_endpoint_reflects_real_request_counts`
hits `/healthz` twice and asserts the counter increased through a real
HTTP round trip, not a mocked registry).

### 5. `IErrorReporter`: `LoggingErrorReporter` default (needs nothing), `SentryErrorReporter` real-but-unverified

Same interface-plus-swap-point shape as every other cross-cutting
concern in this codebase. `LoggingErrorReporter` is real and complete -
a structured `ERROR`-level JSON log line carrying the exception type,
traceback, and whatever request context (`correlation_id`/`user_id`/
`project_id`) was active - needing no account or network call.
`SentryErrorReporter` genuinely calls the real `sentry-sdk` API
(`sentry_sdk.init`, `push_scope`, `capture_exception`) but is
unverified against a live Sentry project (none exists in this
sandbox) - `sentry-sdk` is deliberately not a hard dependency of
`packages/observability` (lazy `import sentry_sdk` inside `__init__`,
confirmed to raise `ModuleNotFoundError` predictably when absent -
`tests/test_observability.py::test_sentry_error_reporter_requires_sentry_sdk_installed`).

### 6. `apps/api`'s global `Exception` handler reads `request.app.state.app_state` directly, not via `Depends` - a real gotcha the first version of its own test caught

`main.py`'s `@app.exception_handler(Exception)` cannot use FastAPI's
dependency injection (`Depends(get_app_state)`) the way every route
handler does - Starlette only ever calls an exception handler with
`(request, exc)`. The first version of
`tests/test_api_observability.py::test_unhandled_exception_returns_generic_body_with_correlation_id_and_reports_it`
used `app.dependency_overrides[get_app_state] = ...` (the pattern every
other test in this codebase already uses to inject a custom `AppState`)
and failed: the spy `IErrorReporter` was never called, because the
handler reads `request.app.state.app_state` directly and
`dependency_overrides` never touches that attribute. Fixed in the test
by patching `app.state.app_state` itself (after the lifespan has set
the real default one) - a genuine, previously-undocumented limitation
of `dependency_overrides` worth recording, not a bug in `main.py`
itself.

### 7. `ObservabilityMiddleware` deliberately never resets the `correlation_id` contextvar

The first version did (`finally: context.reset_correlation_id(token)`),
and a live request against `/__boom` showed the bug immediately: the
500 response body's `correlation_id` field came back `None`, because
`main.py`'s `Exception` handler runs in `ServerErrorMiddleware`, which
sits *outside* `ObservabilityMiddleware` in Starlette's stack - by the
time it runs, the `finally` block had already cleared the contextvar.
Removed the reset entirely; confirmed safe (not just convenient) by
directly testing that a value set inside one request's context is never
visible at the start of the next request's context, without any
explicit reset - each ASGI request dispatches from a fresh
`contextvars.Context`, so a `ContextVar.set()` that's never reset
simply stops mattering once that request's task ends, the same way an
ordinary local variable does.

## Consequences

- `tests/test_observability.py` (12 tests) covers `packages/observability`
  directly: JSON formatting, the context filter, correlation id
  generation, a real captured OpenTelemetry span, tracing-provider
  idempotency, real Prometheus counter/histogram state, both error
  reporters. `tests/test_api_observability.py` (5 tests) covers the
  `apps/api` wiring end-to-end via `TestClient`: correlation id
  generation/propagation, `/metrics` reflecting real traffic, the
  exception handler's correlation-id-bearing non-leaking 500 body and
  real `IErrorReporter` invocation, and confirmation that an ordinary
  409 business-rule rejection never reaches the error reporter.
- Every pre-existing test continues to pass unchanged (475 passed, 6
  skipped - the 6 are the pre-existing Temporal-dev-server-not-running
  skips, unrelated to this ADR) - `configure_logging`/`configure_tracing`
  add a middleware and an exception handler but change no existing
  route's response shape on the success path, and `AppState` gained one
  new required field (`error_reporter`) that every direct-construction
  test site (two, both already updated for `lifecycle` in ADR 0015) now
  also passes.
- `RATE_LIMIT_REJECTIONS_TOTAL` (`metrics.py`) is defined but not yet
  incremented anywhere - it exists ahead of WP5's rate limiter
  (`docs/adr/0020-security-hardening.md`) landing, the same
  "interface/metric ready, consumer follows" pattern used elsewhere in
  this codebase, not a gap specific to this ADR.
- `OTLPSpanExporter`/`SentryErrorReporter` remain genuinely unverified
  against a live collector/Sentry project - both are real, correct SDK
  usage, ready for a real deployment to point at, but this sandbox has
  neither reachable.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`'s public contract, `ProjectLifecycle`'s public
  contract, `IProjectStore`, `IEventBus`, `ITokenStore`/`ICache`, or
  `CinematicIntelligenceCoordinator` - every addition (log calls, span
  wrapping, metric increments) is additive instrumentation inside
  existing methods, not a signature or behavior change. `AppState`
  gaining `error_reporter` is the one new required field, populated
  identically by `build_app_state()` for every caller.
