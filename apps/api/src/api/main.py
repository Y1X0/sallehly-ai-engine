from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from config_sdk import get_settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import assets, auth, cinematic, jobs, projects
from .state import build_app_state


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

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(cinematic.router)
app.include_router(jobs.router)
app.include_router(assets.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
