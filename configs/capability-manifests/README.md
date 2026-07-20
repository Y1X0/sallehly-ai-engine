# configs/capability-manifests

Reserved for environment-level *overrides* of a `models/<engine>/capability_manifest.yaml`
(e.g. a lower `max_shot_duration_sec` cap in a cost-constrained staging
environment). The Model Registry (`models/registry.yaml`) and each
engine's own manifest remain the source of truth — files here, if any,
are merged on top, never replace them wholesale.

**Status:** empty in Phase 0 — no override has been needed yet.
