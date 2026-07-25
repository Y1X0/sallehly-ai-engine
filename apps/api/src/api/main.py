from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from config_sdk import get_settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from observability import configure_logging, configure_tracing, context, render_metrics

from .middleware import ObservabilityMiddleware
from .routes import assets, auth, cinematic, jobs, projects
from .state import AppState, build_app_state

_settings = get_settings()
configure_logging(service_name="sallehly-api", level=_settings.log_level)
configure_tracing(service_name="sallehly-api", exporter=_settings.otel_exporter, otlp_endpoint=_settings.otel_endpoint or None)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.app_state = build_app_state(get_settings())
    yield


app = FastAPI(
    title="Sallehly AI Video Engine API",
    version="0.1.0",
    description="Public/internal API gateway. See docs/api/openapi.yaml for the full contract.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything a route handler didn't already turn into an
    `HTTPException` (a real bug, not a business-rule rejection) -
    reports it via the configured `IErrorReporter` (Phase 8 WP1,
    `docs/adr/0019-observability.md`) and returns a body that never
    leaks internals (no traceback, no exception message) beyond the
    correlation id a caller can hand back to support."""
    state: AppState = request.app.state.app_state
    state.error_reporter.capture_exception(
        exc, extra={"path": request.url.path, "method": request.method}
    )
    correlation_id = context.get_correlation_id()
    body: dict[str, str] = {"detail": "Internal server error"}
    if correlation_id is not None:
        body["correlation_id"] = correlation_id
    return JSONResponse(status_code=500, content=body)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(cinematic.router)
app.include_router(jobs.router)
app.include_router(assets.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
