"""Real, executed tests for packages/observability (Phase 8 WP1): JSON
structured logging + correlation id injection, real OpenTelemetry spans
(captured via the SDK's own `InMemorySpanExporter`, not a stub), real
Prometheus metrics exposition, and the error reporter.
"""

from __future__ import annotations

import json
import logging

import observability as obs
import pytest
from observability.logging import JsonFormatter, _ContextFilter


def _make_record(logger_name: str = "test", message: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord(logger_name, logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_expected_fields():
    record = _make_record(message="hello world", shot_id="shot_0_0")
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["shot_id"] == "shot_0_0"
    assert "timestamp" in payload


def test_json_formatter_includes_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)
    assert "ValueError: boom" in payload["exception"]


def test_context_filter_injects_correlation_id_onto_the_record():
    token = obs.context.set_correlation_id("corr-123")
    try:
        record = _make_record()
        _ContextFilter().filter(record)
        assert record.correlation_id == "corr-123"
    finally:
        obs.context.reset_correlation_id(token)


def test_context_filter_leaves_none_when_no_correlation_id_set():
    record = _make_record()
    _ContextFilter().filter(record)
    assert record.correlation_id is None


def test_configure_logging_and_get_logger_produce_real_json_lines(capsys):
    obs.configure_logging(service_name="test-svc", level="INFO")
    logger = obs.get_logger("test.smoke")
    token = obs.context.set_correlation_id("corr-abc")
    try:
        logger.info("did the thing", extra={"job_id": "job_1"})
    finally:
        obs.context.reset_correlation_id(token)

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["message"] == "did the thing"
    assert payload["correlation_id"] == "corr-abc"
    assert payload["job_id"] == "job_1"
    assert payload["service"] == "test-svc"


def test_new_correlation_id_is_unique_and_short():
    ids = {obs.context.new_correlation_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 16 for i in ids)


def test_traced_span_produces_a_real_span_with_attributes():
    """Real OpenTelemetry SDK end-to-end: a genuine `TracerProvider`
    processes a genuine `Span` through a genuine `SpanProcessor`, and the
    SDK's own `InMemorySpanExporter` (used by OTel's own test suite, not
    a stub written for this project) captures the finished span so its
    name/attributes can be asserted on directly."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    obs.configure_tracing("test-svc", exporter="none")
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with obs.traced_span("test.operation", project_id="proj_1") as span:
        span.set_attribute("extra", "value")

    spans = [s for s in exporter.get_finished_spans() if s.name == "test.operation"]
    assert len(spans) == 1
    assert spans[0].attributes["project_id"] == "proj_1"
    assert spans[0].attributes["extra"] == "value"


def test_configure_tracing_is_idempotent():
    from opentelemetry import trace

    provider_1 = obs.configure_tracing("test-svc", exporter="none")
    provider_2 = obs.configure_tracing("a-different-service-name", exporter="otlp")
    assert provider_1 is provider_2
    assert trace.get_tracer_provider() is provider_1


def test_render_metrics_reflects_real_counter_state():
    before_body, content_type = obs.render_metrics()
    obs.HTTP_REQUESTS_TOTAL.labels(method="GET", path="/__test_metrics_probe", status="200").inc()
    after_body, _ = obs.render_metrics()

    assert content_type.startswith("text/plain")
    assert before_body != after_body
    assert b'path="/__test_metrics_probe"' in after_body
    assert b"sallehly_http_requests_total" in after_body


def test_time_histogram_records_an_observation():
    from prometheus_client import Histogram

    histogram = Histogram("test_only_histogram_seconds", "test-only", registry=obs.REGISTRY)
    with obs.time_histogram(histogram):
        pass
    body, _ = obs.render_metrics()
    assert b"test_only_histogram_seconds_count 1.0" in body


def test_logging_error_reporter_logs_a_structured_error_line(capsys):
    obs.configure_logging(service_name="test-svc", level="INFO")
    reporter = obs.LoggingErrorReporter()
    try:
        raise ValueError("kaboom")
    except ValueError as exc:
        reporter.capture_exception(exc, extra={"shot_id": "shot_0_0"})

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    payload = json.loads(lines[-1])
    assert payload["level"] == "ERROR"
    assert payload["exception_type"] == "ValueError"
    assert payload["shot_id"] == "shot_0_0"
    assert "ValueError: kaboom" in payload["exception"]


def test_sentry_error_reporter_requires_sentry_sdk_installed():
    """`sentry-sdk` is deliberately not a hard dependency of
    packages/observability (same lazy-optional discipline as
    ClaudeProvider/RunPodProvider needing a real API key) - constructing
    `SentryErrorReporter` without it installed fails loudly and
    predictably rather than silently doing nothing."""
    with pytest.raises(ModuleNotFoundError):
        obs.SentryErrorReporter("https://example.invalid/123")
