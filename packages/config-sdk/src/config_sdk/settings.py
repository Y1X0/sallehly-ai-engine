from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sallehly:sallehly@localhost:5432/video_engine"
    """Uses the "+psycopg" (psycopg3) dialect explicitly - SQLAlchemy's
    bare "postgresql://" defaults to psycopg2, which packages/persistence
    does not depend on (see PostgresProjectStore, Phase 8 WP2)."""
    project_store: str = "memory"
    """"memory" (default, InMemoryProjectStore - unchanged from every
    pre-Phase-8 environment) or "postgres" (PostgresProjectStore - real
    Postgres persistence, see docs/adr/0016-postgres-persistence.md)."""
    redis_url: str = "redis://localhost:6379/0"
    event_bus: str = "memory"
    """"memory" (default, InMemoryEventBus - unchanged from every
    pre-Phase-8 environment) or "redis" (RedisEventBus - real cross-
    process pub/sub delivery over redis_url, see
    docs/adr/0017-redis-backed-infra.md)."""
    token_store: str = "memory"
    """"memory" (default, InMemoryTokenStore - unchanged from every
    pre-Phase-8 environment) or "redis" (RedisTokenStore - bearer tokens
    recognized across every apps/api process sharing redis_url)."""
    cache_backend: str = "memory"
    """"memory" (default, InMemoryCache) or "redis" (RedisCache)."""

    storage_provider: str = "local"
    """"local" (default, LocalFilesystemStorageProvider - unchanged from
    every pre-Phase-8 environment) or "s3" (S3Provider - a real
    S3-compatible backend at storage_endpoint_url, see
    docs/adr/0018-s3-storage-provider.md)."""
    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "video-engine-assets"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "sallehly-project-lifecycle"

    orchestrator: str = "sync"
    """"sync" (default, SyncProjectOrchestrator - unchanged from every
    pre-Phase-8 environment) or "temporal" (TemporalProjectOrchestrator -
    durable, crash-resumable; requires a real Temporal server at
    temporal_address/temporal_namespace plus a worker process running
    render_orchestrator.workflows.build_worker - see
    docs/adr/0015-temporal-activation.md)."""

    llm_provider: str = "claude"
    anthropic_api_key: str = ""

    video_engine: str = "wan2.1"
    compute_provider: str = "local"

    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    vastai_api_key: str = ""
    vastai_instance_host: str = ""

    cors_allowed_origins: str = "http://localhost:3000"
    """Comma-separated origins apps/api allows via CORS - the frontend's own
    origin, since browsers enforce this for cross-origin fetch()/XHR."""

    log_level: str = "INFO"
    otel_exporter: str = "console"
    """"console" (default, ConsoleSpanExporter - genuinely runs with no
    external collector) / "otlp" (real OTLPSpanExporter at otel_endpoint,
    needs a reachable collector) / "none" (tracing disabled). See
    docs/adr/0019-observability.md."""
    otel_endpoint: str = ""
    error_reporter: str = "logging"
    """"logging" (default, LoggingErrorReporter - structured JSON log
    line, no account needed) or "sentry" (SentryErrorReporter - needs
    sentry_dsn)."""
    sentry_dsn: str = ""

    rate_limiter: str = "memory"
    """"memory" (default, InMemoryRateLimiter) or "redis" (RedisRateLimiter -
    correct across multiple apps/api processes). See
    docs/adr/0020-security-hardening.md."""
    auth_rate_limit_per_minute: int = 20
    """Applies to POST /auth/register and /auth/login, keyed by client
    IP (no authenticated user exists yet at that point)."""
    generation_rate_limit_per_minute: int = 10
    """Applies to POST .../generate-video and .../retry-generation,
    keyed by user id."""

    token_store_ttl_seconds: int = 0
    """0 (default) = tokens never expire, unchanged from every pre-WP5
    environment. A positive value makes LocalAuthProvider-issued tokens
    expire after that many seconds - InMemoryTokenStore/RedisTokenStore
    both honor it (see docs/adr/0020-security-hardening.md)."""

    upload_max_bytes: int = 25 * 1024 * 1024
    upload_allowed_content_types: str = "image/png,image/jpeg,image/webp,image/gif"
    """Comma-separated allowlist for POST /assets/upload's Content-Type."""

    quota_enforcer: str = "memory"
    """"memory" (default, InMemoryQuotaEnforcer) or "redis"
    (RedisQuotaEnforcer - correct across multiple apps/api processes)."""
    max_concurrent_generations_per_workspace: int = 0
    """0 (default) = unlimited, unchanged from every pre-WP5
    environment. A positive value caps how many generate_video calls one
    workspace may have in flight at once (docs/PHASE8_SCALEOUT_PLAN.md
    items 7/25)."""


def get_settings() -> Settings:
    return Settings()
