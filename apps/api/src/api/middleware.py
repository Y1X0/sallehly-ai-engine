from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from observability import context, get_logger
from observability.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL
from observability.tracing import get_tracer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_logger = get_logger("api.request")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """One middleware for the per-request cross-cutting concerns that all
    need the same before/after hook (Phase 8 WP1): correlation id
    propagation (`X-Correlation-ID` request header read or generated,
    always echoed back on the response), structured request logging, a
    real OpenTelemetry span wrapping the whole request, and Prometheus
    request-count/duration metrics.

    Records the request (metric + log) even when the route handler
    raises - `except Exception: self._record(...); raise` - since a
    500 is still a real HTTP response with real duration worth
    measuring, not just the happy path. Actual error *reporting*
    (`IErrorReporter.capture_exception`) happens in `main.py`'s
    `Exception` handler, not here - `ServerErrorMiddleware` (which
    dispatches that handler) sits *outside* this middleware in
    Starlette's stack, so the request has already unwound past this
    middleware's `except` clause by the time it fires.

    Deliberately does NOT `context.reset_correlation_id()` after the
    request: `main.py`'s `Exception` handler runs even further outside
    this middleware (same reason as above) and needs to still read the
    correlation id to put it in the 500 body - resetting here would
    already have cleared it by the time that handler runs. This is safe
    without a leak risk: each ASGI request is dispatched from a fresh
    `contextvars.Context` (confirmed empirically - a value set inside
    one request is never visible at the start of the next), so a
    `ContextVar.set()` that's never explicitly reset simply stops
    mattering once the request's task ends, the same way a normal local
    variable does.

    Also mirrors the correlation id onto `request.state.correlation_id`,
    not just the contextvar: `BaseHTTPMiddleware.call_next()` spawns a
    new child task per stacked `BaseHTTPMiddleware` layer, and a
    `ContextVar.set()` made inside that child task is invisible once
    control returns to the parent task - which is exactly the boundary
    `main.py`'s exception handler sits across (in `ServerErrorMiddleware`,
    outside every user-added middleware, including `SecurityHeadersMiddleware`
    added below). `request.state` is backed by the ASGI `scope` dict,
    passed by reference through every nested task spawn, so it survives
    that boundary where the contextvar does not (confirmed empirically).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-correlation-id")
        correlation_id = incoming or context.new_correlation_id()
        context.set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        tracer = get_tracer("sallehly.api")
        with tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.target", request.url.path)
            span.set_attribute("correlation_id", correlation_id)
            try:
                response = await call_next(request)
            except Exception:
                self._record(request, 500, start)
                raise
            span.set_attribute("http.status_code", response.status_code)
        self._record(request, response.status_code, start)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @staticmethod
    def _record(request: Request, status_code: int, start: float) -> None:
        duration = time.perf_counter() - start
        label_path = _route_template(request)
        HTTP_REQUESTS_TOTAL.labels(method=request.method, path=label_path, status=str(status_code)).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, path=label_path).observe(duration)
        _logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": label_path,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

_DEMO_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self'"
)
"""GET /demo (apps/api/src/api/static/demo.html) is the one route this
API serves that is actually an HTML page with its own inline
script/style and same-origin fetch() calls - `default-src 'none'` (safe
for every JSON route, which is everything else this API serves) would
break it outright. Scoped to the `/demo` prefix only; every other
route keeps the strict default unchanged."""


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds a fixed set of defensive response headers to every request
    (Phase 8 WP5, `docs/PHASE8_SCALEOUT_PLAN.md` item 23 "secure
    headers"). `apps/api` is a JSON API, never HTML/JS - `default-src
    'none'` is safe precisely because there's no page here that ever
    needs to load a script/style/image of its own. `Strict-Transport-Security`
    only actually does anything once a deployment terminates TLS in
    front of this process; sending it unconditionally is harmless over
    plain HTTP (browsers ignore `Strict-Transport-Security` on a
    non-HTTPS response) and one less thing to get wrong at deploy time.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        apply_security_headers(response, path=request.url.path)
        return response


def apply_security_headers(response: Response, *, path: str = "") -> Response:
    """Also called directly by `main.py`'s global `Exception` handler:
    that handler builds its `JSONResponse` inside `ServerErrorMiddleware`,
    which sits *outside* `SecurityHeadersMiddleware` in Starlette's
    stack (same reason `ObservabilityMiddleware` can't record a
    500-from-an-exception through its own `call_next` either) - a
    response built there never passes back through this middleware's
    `dispatch`, so it needs these headers applied explicitly.

    `path` selects the relaxed `/demo`-only CSP (see
    `_DEMO_CONTENT_SECURITY_POLICY`); every other path (including the
    default, unknown-path case) keeps the strict `default-src 'none'`."""
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    if path.startswith("/demo"):
        response.headers["Content-Security-Policy"] = _DEMO_CONTENT_SECURITY_POLICY
    return response


def _route_template(request: Request) -> str:
    """Prefers the matched route's path *template*
    (`/projects/{project_id}`) over the raw URL path
    (`/projects/proj_abc123`) for metric labels - using raw paths would
    make `sallehly_http_requests_total` grow one label combination per
    unique project/job/shot id ever requested, defeating the point of a
    bounded-cardinality metric. Starlette's router sets `scope["route"]`
    during dispatch, before the endpoint runs - by the time `call_next`
    has returned, it's already populated for any route that matched."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path
