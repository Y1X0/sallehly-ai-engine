# packages/config-sdk

## Config SDK

**Responsibility:** Typed access to per-environment configuration and per-tenant feature flags (configs/environments/*.yaml), and the small provider/engine/compute registries (`ENGINE_REGISTRY`, `COMPUTE_REGISTRY`, an equivalent for `ILLMProvider`) that let every swap point in the system be driven by config rather than code changes.

**Input:** `configs/environments/*.yaml`, environment variables (see `.env.example`)

**Output:** Typed `Settings` object + registry lookups by string id

**Consumed by:** Every service

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 0/1 target - see `docs/ARCHITECTURE.md#roadmap`.
