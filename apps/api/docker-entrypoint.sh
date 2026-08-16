#!/bin/sh
# Production entrypoint: runs the real Alembic migration before the API
# starts accepting traffic, when PROJECT_STORE=postgres - the same
# `cd packages/persistence && uv run alembic upgrade head` sequence
# docs/DEV_SETUP.md documents as a manual local step, now automated for
# the actual deployment path (docs/PRODUCTION_READINESS_CHECKLIST.md
# flagged this as missing). Skipped entirely for the default
# PROJECT_STORE=memory (InMemoryProjectStore has no schema to migrate),
# so this never blocks a non-Postgres deployment of this same image.
set -e

if [ "$PROJECT_STORE" = "postgres" ]; then
  echo "PROJECT_STORE=postgres - running 'alembic upgrade head' before startup"
  (cd /app/packages/persistence && uv run alembic upgrade head)
fi

# Respects docker-compose.yml's own `command:` override (e.g. adding
# --reload for local dev) instead of always hardcoding the same
# uvicorn invocation - falls back to the plain production command when
# no arguments are passed (this Dockerfile's CMD is gone in favor of
# this default, so a bare `docker run <image>` still works).
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
fi
