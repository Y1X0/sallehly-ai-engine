from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from config_sdk import get_settings
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from observability import configure_logging, configure_tracing, context, render_metrics

from .middleware import ObservabilityMiddleware, SecurityHeadersMiddleware, apply_security_headers
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
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything a route handler didn't already turn into an
    `HTTPException` (a real bug, not a business-rule rejection) -
    reports it via the configured `IErrorReporter` (Phase 8 WP1,
    `docs/adr/0019-observability.md`) and returns a body that never
    leaks internals (no traceback, no exception message) beyond the
    correlation id a caller can hand back to support.

    Reads the correlation id from `request.state` (falling back to the
    contextvar) rather than solely `context.get_correlation_id()`:
    `ServerErrorMiddleware` (which dispatches this handler) sits outside
    every stacked `BaseHTTPMiddleware`, and `ObservabilityMiddleware`'s
    own `ContextVar.set()` doesn't survive that boundary once a second
    `BaseHTTPMiddleware` (`SecurityHeadersMiddleware`) is also stacked -
    see `middleware.py`. `request.state` does survive it."""
    state: AppState = request.app.state.app_state
    correlation_id = getattr(request.state, "correlation_id", None) or context.get_correlation_id()
    state.error_reporter.capture_exception(
        exc, extra={"correlation_id": correlation_id, "path": request.url.path, "method": request.method}
    )
    body: dict[str, str] = {"detail": "Internal server error"}
    if correlation_id is not None:
        body["correlation_id"] = correlation_id
    return apply_security_headers(JSONResponse(status_code=500, content=body), path=request.url.path)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(cinematic.router)
app.include_router(jobs.router)
app.include_router(assets.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


_STATIC_DIR = Path(__file__).parent / "static"
_DEMO_DATA_ROOT = (Path.cwd() / ".docker-data").resolve()
"""Sandbox for GET /demo/asset-content: both `LocalProvider` (render
stubs) and `LocalFilesystemStorageProvider` (registered assets) default
to paths under `./.docker-data` (see apps/api/src/api/state.py) - this
demo-only endpoint refuses to read anything outside that directory."""


@app.get("/demo")
def demo_page() -> FileResponse:
    """Serves the zero-setup click-through demo (apps/api/src/api/static/demo.html):
    prompt in, real CreativeDirector/ShotPlanner/CreativeCompiler/
    ProjectLifecycle pipeline runs, mock-rendered artifacts out. Uses the
    same running server and its default (offline, in-memory) AppState -
    no separate build step or frontend project required."""
    return FileResponse(_STATIC_DIR / "demo.html")


@app.get("/demo/asset-content")
def demo_asset_content(uri: str) -> Response:
    """Lets the demo page preview a generated artifact's content. Assets
    from the default local mock pipeline are `file://` paths under
    `.docker-data/` (LocalProvider's render stubs, or
    LocalFilesystemStorageProvider's uploads) - this reads and returns
    that file's raw content, refusing anything outside `.docker-data/`
    to keep this demo convenience from becoming an arbitrary file read.
    """
    if not uri.startswith("file://"):
        raise HTTPException(status_code=400, detail="Only file:// asset URIs can be previewed here")
    path = Path(uri.removeprefix("file://")).resolve()
    if _DEMO_DATA_ROOT != path and _DEMO_DATA_ROOT not in path.parents:
        raise HTTPException(status_code=403, detail="Refusing to read a path outside .docker-data/")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No such file: {path}")
    return Response(content=path.read_text(), media_type="application/json")


@app.get("/metrics")
def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
