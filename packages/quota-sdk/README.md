# packages/quota-sdk

`IQuotaEnforcer` - a per-scope concurrency cap, not a rate limit (Phase
8 WP5, see `docs/adr/0020-security-hardening.md`). Bounds how many
operations for a given scope (a workspace id) may be *in flight* at
once - `docs/PHASE8_SCALEOUT_PLAN.md` items 7 and 25 - protecting
against one workspace exhausting GPU capacity or running up an
unbounded bill via unlimited simultaneous `generate_video` calls.

Two implementations, selected via `Settings.quota_enforcer`
(`"memory"` default / `"redis"`, `apps/api/state.py`):

- **`InMemoryQuotaEnforcer`**: a lock-protected in-process counter dict.
- **`RedisQuotaEnforcer`**: the check-and-increment runs inside a single
  Lua script (`EVAL`), executed atomically by Redis - correct across
  multiple `apps/api` processes racing for the same workspace's last
  slot, unlike a naive `INCR` + check + `DECR`-on-reject sequence.

## Interface

```
IQuotaEnforcer.acquire(scope, *, max_concurrent) -> None   # raises QuotaExceededError if already at capacity
IQuotaEnforcer.release(scope) -> None
```

## Wired into

`ProjectLifecycle._run_generation` (`services/render-orchestrator`) -
`acquire()`s the project's `workspace_id` before calling
`GenerationPipeline.generate_plan()`, `release()`s in a `finally`
regardless of success/failure. `None` by default (unlimited, identical
behavior to every pre-WP5 environment) - only enforced when
`Settings.max_concurrent_generations_per_workspace > 0`.
