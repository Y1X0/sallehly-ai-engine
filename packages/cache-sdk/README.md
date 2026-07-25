# packages/cache-sdk

`ICache` - a generic key/value cache abstraction (Phase 8 WP3). Two
implementations, selected via `Settings.cache_backend` (`"memory"`
default / `"redis"`, `apps/api/state.py`):

- **`InMemoryCache`**: process-local dict, with an application-level TTL
  check on `get()`. The default for every test in this repo and local
  dev with no Redis running.
- **`RedisCache`** (Phase 8 WP3, `docs/adr/0017-redis-backed-infra.md`):
  a real Redis server via `redis-py`, `ttl_seconds` mapped directly onto
  Redis's own key expiry (`SET ... EX`).

Both store values JSON-serialized (even `InMemoryCache`, deliberately -
see the docstring on `ICache`), so a value that works under
`InMemoryCache` in tests is guaranteed to also work once
`CACHE_BACKEND=redis` is selected.

## Interface

```
ICache.get(key) -> Any | None
ICache.set(key, value, ttl_seconds=None) -> None
ICache.delete(key) -> None
```
