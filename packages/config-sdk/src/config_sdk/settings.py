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


def get_settings() -> Settings:
    return Settings()
