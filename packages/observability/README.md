# packages/observability

## Observability

**Responsibility:** Shared OpenTelemetry setup (tracing/metrics), structured logging configuration, and helpers for tagging spans with project_id/shot_id/engine_id so a single render can be traced end-to-end across every service it touches.

**Input:** N/A (cross-cutting library)

**Output:** Configured tracer/logger instances

**Consumed by:** Every service

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 4 target - see `docs/ARCHITECTURE.md#roadmap`.
