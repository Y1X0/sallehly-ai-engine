# infra/docker

Shared Docker resources (base images, compose overrides for
staging/production) beyond the per-service `Dockerfile`s that live next to
their code (`apps/api/Dockerfile`, `workers/gpu-worker/Dockerfile`). Local
dev's `docker-compose.yml` lives at the repo root, not here, since it
composes services across the whole monorepo.
