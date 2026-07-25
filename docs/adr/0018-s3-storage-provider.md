# ADR 0018: S3-compatible `IStorageProvider` (Phase 8 WP4)

**Status:** Accepted

## Context

`docs/PHASE8_SCALEOUT_PLAN.md`'s WP4 named a real `S3Provider(IStorageProvider)`
as the last piece of "databases and storage" (the user's own phrase for
what to do after WP6) - `LocalFilesystemStorageProvider` writes bytes to
a local directory and returns `file://` URIs, which cannot be shared
across separate API/worker processes or survive a container being
recycled, the same class of gap ADR 0016/0017 already closed for project
records, events, and tokens.

The plan's own text said to "test against the already-running MinIO
container first." Neither that container nor any other path to a real
MinIO server turned out to be reachable in this sandbox:
`docker pull minio/minio` hits the same blocked Docker Hub registry
ADR 0015/0016 already hit for `temporalio/admin-tools`/`postgres`, and a
direct MinIO binary download (`dl.min.io`) is also blocked at the
network-policy level - confirmed via the agent-proxy's
`recentRelayFailures` (`connect_rejected`, `gateway answered 403 to
CONNECT`, `host: dl.min.io:443`), the same diagnostic method used for
every other blocked-host finding in this project.

Unlike Temporal (where a GitHub Releases binary download was a real,
unblocked alternative path to a live server), no equivalent path exists
for MinIO here. Rather than leave `S3Provider` "structurally validated
only" - the discipline this whole project has treated as a fallback of
last resort, not a first choice - `moto`'s `ThreadedMotoServer` was used
instead: not a client-side response-stubbing mock, but a real, separate
HTTP server process (started in a background thread, listening on a
real local port) that implements the actual S3 REST API - the same
server AWS's own SDK test suites are built against. `S3Provider`'s
`boto3` client talks to it over genuine HTTP, exactly as it would talk
to a real MinIO or AWS S3 endpoint via `endpoint_url`.

## Decisions

### 1. `S3Provider(IStorageProvider)` via `boto3`, `endpoint_url` is what makes it S3-*compatible*

`packages/storage-sdk/src/storage_sdk/s3_provider.py`. `boto3.client("s3",
endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=...)` -
`endpoint_url=None` talks to real AWS S3; any other value (a MinIO
deployment, Cloudflare R2, Backblaze B2, ...) works identically, since
all of them speak the same S3 REST API `boto3` targets. This is the
same "one real client library, endpoint is config" shape
`RunPodProvider`/`PostgresProjectStore`/`RedisCache` already use.

### 2. `get_uri()` returns `s3://<bucket>/<key>`, not a fetchable HTTP URL

Mirrors `LocalFilesystemStorageProvider`'s `file://` URI shape - a
stable, storage-agnostic identifier `AssetManager` and `ProjectRecord`
can hold, not something a browser can `GET` directly (a private bucket
has no public HTTP URL at all). Generating actual client-facing URLs
(presigned, time-limited, or a CDN in front of a public bucket) is
`docs/PHASE8_SCALEOUT_PLAN.md` item 26 (signed URLs, WP11) - a distinct,
not-yet-built concern this ADR does not attempt.

### 3. Real tests run against `moto.server.ThreadedMotoServer`, not `@mock_aws`-style decorators

`tests/test_s3_provider.py` starts one real `ThreadedMotoServer` per
test module (a genuine background-thread HTTP server on a real port,
`server.get_host_and_port()`), constructs `S3Provider` pointed at it via
`endpoint_url`, and - critically - one test reads an uploaded object
back through a **second, independently-constructed `boto3` client**
rather than the same provider instance, to prove the upload is a real
round trip through the server and not an artifact of shared in-process
state. `moto[server]` (pulling in `flask`/`werkzeug`) is a `dev`
dependency-group addition (`pyproject.toml`), not a `storage-sdk`
runtime dependency - it exists only to stand up this real test server,
the same role a natively-installed Postgres/Redis server plays for
ADR 0016/0017's tests.

### 4. `STORAGE_PROVIDER=local|s3`, defaulting to `local` - same swap-point discipline as `PROJECT_STORE`/`EVENT_BUS`/`TOKEN_STORE`/`CACHE_BACKEND`

`config_sdk.Settings.storage_provider` (default `"local"`) selects
between `LocalFilesystemStorageProvider` and `S3Provider` in
`apps/api/state.py`'s `build_app_state()`, reusing the
`storage_endpoint_url`/`storage_access_key`/`storage_secret_key`/
`storage_bucket` fields that already existed in `Settings` (added early
in the project in anticipation of this work but never actually read by
`apps/api` until now - the same kind of real, previously-undetected gap
ADR 0014 found for `VIDEO_ENGINE_REGISTRY`). Same lazy-import discipline
(`boto3`/`S3Provider` only imported when `s3` is actually selected) as
every other swap point in this function.

## Consequences

- `tests/test_s3_provider.py` (5 tests) is genuinely executed against a
  real, separately-running S3-compatible HTTP server - not skipped by
  default the way the Postgres/Redis tests are when their server isn't
  reachable, since `moto[server]` is a `dev`-group dependency already
  installed for every environment that runs this test suite at all, so
  there is no "unreachable" case to guard against here. A live end-to-end
  smoke test additionally confirmed `STORAGE_PROVIDER=s3` wired through
  `build_app_state()` writes and reads a real object via the same moto
  server (not included in the automated suite - a one-off verification,
  documented here rather than silently relied upon).
- This is honestly a different rigor tier than ADR 0016/0017's tests,
  which run against the exact real backend (Postgres/Redis) a production
  deployment would use. `S3Provider`'s production correctness rests on
  `boto3` and the S3 REST API being genuinely standardized across
  providers (true in practice - `moto` itself is validated against real
  AWS behavior by its maintainers) rather than on this project having
  exercised a real MinIO/S3/R2 endpoint directly. A real MinIO
  smoke-test is recommended before this path is trusted in a genuine
  production deployment, even though nothing here is faked or
  mocked-in-the-weak-sense.
- `apps/api`'s default behavior is unchanged - `STORAGE_PROVIDER`
  defaults to `local`, and every pre-WP4 test/environment is unaffected.
  Selecting `s3` is opt-in and config-driven.
- Signed/presigned URL generation (item 26, WP11) remains unimplemented
  - `get_uri()`'s `s3://` scheme is ready for a future caller to resolve
    into a real fetchable URL, but no caller does that yet.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`, `ProjectLifecycle`, `IProjectStore`, `IEventBus`,
  `ITokenStore`/`ICache`, or `CinematicIntelligenceCoordinator` in any
  way - `S3Provider` is a new implementation of `IStorageProvider`, the
  interface every caller (`AssetManager`) already depended on
  exclusively. This closes out `docs/PHASE8_SCALEOUT_PLAN.md`'s
  "databases and storage" scope (WP2/WP3/WP4) per the user's explicit
  instruction to do WP6 first, then databases and storage.
