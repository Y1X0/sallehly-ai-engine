from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Sallehly AI Video Engine API",
    version="0.1.0",
    description="Public/internal API gateway. See docs/api/openapi.yaml for the full contract.",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Phase 1+: mount routers for /v1/projects, /v1/projects/{id}/storyboard,
# /v1/render-jobs, etc. once ai-director and the creative compiler pipeline
# are wired up. See docs/api/openapi.yaml for the target contract.
