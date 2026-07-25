# packages/rate-limit-sdk

`IRateLimiter` - fixed-window request-rate limiting (Phase 8 WP5, see
`docs/adr/0020-security-hardening.md`). Two implementations, selected
via `Settings.rate_limiter` (`"memory"` default / `"redis"`,
`apps/api/state.py`):

- **`InMemoryRateLimiter`**: process-local counters. The default for
  every test in this repo and local dev with no Redis running.
- **`RedisRateLimiter`**: atomic `INCR`/`EXPIRE` against a real Redis
  server - correct across multiple `apps/api` processes, unlike
  `InMemoryRateLimiter` (which each process enforces independently,
  effectively multiplying the real limit by process count).

## Interface

```
IRateLimiter.allow(key, *, limit, window_seconds) -> RateLimitResult(allowed, remaining, retry_after_seconds)
```

`key` scopes the limiter (e.g. `f"auth_login:{client_ip}"` or
`f"generate_video:{user_id}"`) - the interface only counts, callers own
identity.

## Wired into

`apps/api/src/api/rate_limit.py`'s `rate_limit_by_ip`/`rate_limit_by_user`
FastAPI dependency factories, applied to `/auth/register`, `/auth/login`
(by client IP - no authenticated user exists yet), and
`/projects/{id}/generate-video`, `/projects/{id}/retry-generation` (by
user id - GPU-triggering endpoints, `docs/PHASE8_SCALEOUT_PLAN.md` items
7/23/25).
