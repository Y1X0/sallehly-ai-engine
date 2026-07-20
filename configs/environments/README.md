# configs/environments

Per-environment configuration, loaded by `packages/config-sdk`. Secrets
never live in these files — they come from `.env`/the deployment
platform's secret manager; these YAML files hold non-secret structural
config (which provider/engine/compute-backend is active, feature flags).

`configs/capability-manifests/` intentionally does not duplicate
`models/<engine>/capability_manifest.yaml` — the Model Registry
(`models/registry.yaml`) is the single source of truth for those; this
directory is reserved for environment-level *overrides* of a manifest
(e.g. a lower `max_shot_duration_sec` cap in a cost-constrained staging
environment) should that ever be needed.
