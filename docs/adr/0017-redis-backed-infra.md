# ADR 0017: Redis-backed cache, event bus, and token store (Phase 8 WP3)

**Status:** Accepted

## Context

`docs/PHASE8_SCALEOUT_PLAN.md`'s WP3 named three independent gaps that
all share one fix - a real Redis server, already reachable in this
sandbox at `redis://localhost:6379/0` (natively installed via
`apt`/`redis-server`, not Docker - the same reason ADR 0015/0016 avoided
`docker pull` for Temporal/Postgres):

1. **No cache layer at all.** `docs/PHASE8_SCALEOUT_PLAN.md` item 10
   named three candidates (capability-manifest lookups, prompt-template
   renders, project-list pagination) without committing to one.
2. **`InMemoryEventBus` only delivers within one process.** Its own
   docstring already named this; ADR 0015's Consequences named the
   concrete case where it bites - an `apps/api` process and a separate
   Temporal worker process can't share event delivery through it.
3. **`LocalAuthProvider._tokens` was a plain in-process `dict`.**
   `docs/PHASE8_SCALEOUT_PLAN.md` item 22 named the same multi-replica
   gap: a token issued by one `apps/api` process is unrecognized by
   another.

Every claim below was verified by actually running it against the live
local Redis server, the same bar ADR 0015/0016 set.

## Decisions

### 1. `packages/cache-sdk`: `ICache` + `InMemoryCache` + `RedisCache`, both JSON-serializing

A new package, following the same shape as `packages/persistence`'s
`IProjectStore` pair. `InMemoryCache` round-trips values through
`json.dumps`/`json.loads` too, deliberately - not because it needs to
(a plain dict of live objects would work), but so a value that passes
under `InMemoryCache` in tests is guaranteed to still work the moment
`CACHE_BACKEND=redis` is selected, rather than silently depending on
Python object identity/mutability that only `InMemoryCache` happens to
preserve.

### 2. The demonstrated cache consumer is `engine.capabilities()`, chosen as the lowest-risk of the three candidates - not the highest-leverage one

`apps/api/state.py`'s `_get_cached_capability_manifest()` caches
`IVideoEngine.capabilities()` (a `CapabilityManifest`, serialized via
`dataclasses.asdict`/reconstructed via `CapabilityManifest(**...)`,
since it isn't itself JSON-native - it has a `tuple` field) keyed by
`video_engine`, `ttl_seconds=3600`. This is honestly the least valuable
of the plan's three candidates in terms of runtime savings (`build_app_state()`
already only calls `engine.capabilities()` once per process today) - it
was chosen specifically *because* it's pure, JSON-shaped, and
side-effect-free, making it the safest way to prove the `ICache`
plumbing (get/set/miss/hit, cross-instance read-back) actually works
end-to-end against real Redis before a higher-leverage but riskier
target (prompt-template renders, which touch `packages/prompt-engine`'s
existing `lru_cache`-based loader) gets the same treatment in a later
pass.

### 3. `RedisEventBus`: one Redis channel per `EventType`, `redis-py`'s `pubsub.run_in_thread`

`services/render-orchestrator/src/render_orchestrator/redis_event_bus.py`.
`publish()` is `PUBLISH` on `key_prefix + event_type.value`; `subscribe()`
registers a per-channel callback and lazily starts exactly one
background listener thread on first use. A real bug the live server
caught immediately: the first `close()` implementation called
`self._pubsub.close()` right after `thread.stop()`, racing
`PubSubWorkerThread.run()`'s own `pubsub.close()` call once its loop
exits (`redis-py` source: `stop()` only trips a flag, the thread's own
run loop does the actual close after its current blocking read
returns) - two threads closing the same socket raised
`ValueError: I/O operation on closed file` inside the background
thread, caught by pytest as an unhandled thread exception. Fixed by
`join()`-ing the thread instead of closing the pub/sub connection
directly a second time.

### 4. `packages/auth`: `ITokenStore` extracted from `LocalAuthProvider`, `InMemoryTokenStore`/`RedisTokenStore` behind it

`LocalAuthProvider.__init__` gained an optional `token_store:
ITokenStore | None = None` parameter (defaults to `InMemoryTokenStore`,
behaviorally identical to the old internal `dict[str, str]` - every
existing call site and test is unaffected). `RedisTokenStore` maps
`ttl_seconds` directly onto Redis's own key expiry. This is storage
only, not the expiry/refresh *policy* - `docs/PHASE8_SCALEOUT_PLAN.md`
item 22's "token expiry + refresh" is WP5's job, not this ADR's.

### 5. `EVENT_BUS=memory|redis`, `TOKEN_STORE=memory|redis`, `CACHE_BACKEND=memory|redis`, all defaulting to `memory` - same swap-point discipline as `ORCHESTRATOR`/`PROJECT_STORE`

Three independent `config_sdk.Settings` fields, each wired in
`apps/api/state.py`'s `build_app_state()` with the same lazy-import
discipline (`redis`/`cache_sdk.RedisCache`/`render_orchestrator.redis_event_bus.RedisEventBus`/
`auth.RedisTokenStore` only imported when actually selected) every prior
swap point in this function already uses.

## Consequences

- `tests/test_cache_sdk.py` (11 tests, `InMemoryCache` and `RedisCache`
  parametrized together plus one Redis-only cross-instance test),
  `tests/test_redis_event_bus.py` (5 tests, including cross-instance
  delivery simulating separate API/worker processes and a check that
  handlers run on the listener thread, not the publisher's), and
  `tests/test_redis_token_store.py` (6 tests, including
  `LocalAuthProvider` wired to a real `RedisTokenStore` end-to-end) are
  all genuinely executed against the live local Redis server - skipped,
  not failed, when none is reachable.
- Combined with ADR 0015/0016, an `apps/api` process and a Temporal
  worker process can now share event delivery (`EVENT_BUS=redis`) and
  bearer-token recognition (`TOKEN_STORE=redis`) across genuinely
  separate OS processes, on top of already sharing project state
  (`PROJECT_STORE=postgres`) - closing every remaining piece of the
  multi-process gap ADR 0015's Consequences first named.
- `apps/api`'s default behavior is completely unchanged - all three
  settings default to `memory`, and every pre-WP3 test/environment is
  unaffected. Selecting `redis` for any of the three is opt-in and
  independent of the other two.
- Prompt-template-render caching and project-list-pagination caching
  (`docs/PHASE8_SCALEOUT_PLAN.md` item 10's other two candidates) remain
  unimplemented - `ICache` is ready for either, but wiring a second
  consumer is deliberately left for a later pass rather than claimed
  here.
- Token expiry/refresh policy (item 22) and rate limiting (WP5) are
  unimplemented - `RedisTokenStore`'s `ttl_seconds` parameter is ready
  for that policy to use, but no caller sets it yet.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`, `ProjectLifecycle`, `IProjectStore`, or
  `CinematicIntelligenceCoordinator` in any way - `RedisCache`,
  `RedisEventBus`, and `RedisTokenStore` are new implementations of
  interfaces (`ICache` new in this ADR; `IEventBus`/`ITokenStore`
  already existing or extracted unchanged in shape) that every caller
  already depended on exclusively.
