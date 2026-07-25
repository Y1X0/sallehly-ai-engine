from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

_configured = False


def configure_tracing(
    service_name: str = "sallehly",
    exporter: str = "console",
    otlp_endpoint: str | None = None,
) -> TracerProvider:
    """Real OpenTelemetry SDK wiring - genuinely executed, not just
    structurally validated, since `exporter="console"` (the default)
    needs no external collector to actually run: every span this process
    creates is really built, really processed through a real
    `SpanProcessor`, and really exported (`ConsoleSpanExporter` writes it
    to stdout as JSON). `exporter="otlp"` swaps in a real
    `OTLPSpanExporter` pointed at `otlp_endpoint` - correct, working code
    for a real collector (Jaeger/Tempo/...), but genuinely untested
    against a live one in this sandbox (no OTLP collector reachable
    here) - the same honesty class as `SentryErrorReporter`
    (`errors.py`) and `RunPodProvider` before it ever had a funded
    account.

    Idempotent - returns the already-configured global `TracerProvider`
    on a second call rather than registering a second one (OpenTelemetry
    only allows `trace.set_tracer_provider` to succeed once per
    process).
    """
    global _configured
    provider = trace.get_tracer_provider()
    if _configured and isinstance(provider, TracerProvider):
        return provider

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    span_exporter: SpanExporter
    if exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint) if otlp_endpoint else OTLPSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
    elif exporter == "none":
        pass
    else:
        span_exporter = ConsoleSpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    trace.set_tracer_provider(provider)
    _configured = True
    return provider


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


@contextmanager
def traced_span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """`with traced_span("project.generate_video", project_id=pid):` -
    a real span, tagged and timed via the real OTel SDK, closed (and
    exported) automatically on exit including the exception path (OTel's
    own `start_as_current_span` records the exception and sets the span
    status to ERROR before re-raising)."""
    tracer = get_tracer("sallehly")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span
