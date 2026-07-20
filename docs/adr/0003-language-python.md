# ADR 0003: Python across the entire backend

**Status:** Accepted (per explicit decision from the project owner)

## Context

Wan2.1 and any future custom foundation model run on PyTorch. The
Creative Compiler pipeline (Scene/Camera/Motion/Lighting/Style planners)
is business logic with no inherent language requirement, but it sits
directly between the AI Director and the Video Engine Adapter in every
request.

## Decision

Every backend service (`apps/api`, all of `services/*`, all of
`packages/*`) is Python, using `FastAPI` where an HTTP surface is needed
and plain modules otherwise. `uv` manages the monorepo as a single
workspace (`pyproject.toml` at root, `[tool.uv.workspace]`).

The frontend (`apps/web-dashboard`, Phase 6) remains Next.js/TypeScript —
this decision is about the backend only.

## Consequences

- No cross-language serialization boundary between the Creative Compiler
  and the Video Engine Adapter/GPU worker — a `RenderSpec` is the same
  Python object (or its `dict` form) from compilation to the point it's
  handed to `IVideoEngine.build_job_payload`.
- One dependency/build/test toolchain for the whole backend.
- `packages/schemas`'s JSON Schemas remain the source of truth (not
  Python-only), so they stay valid if any future service is written in
  another language (e.g. a Rust GPU worker) — they are not tied to this
  decision.
