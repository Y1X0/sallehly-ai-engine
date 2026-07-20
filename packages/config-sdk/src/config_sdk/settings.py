from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sallehly:sallehly@localhost:5432/video_engine"
    redis_url: str = "redis://localhost:6379/0"

    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "video-engine-assets"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"

    llm_provider: str = "claude"
    anthropic_api_key: str = ""

    video_engine: str = "wan2.1"
    compute_provider: str = "local"

    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    vastai_api_key: str = ""
    vastai_instance_host: str = ""


def get_settings() -> Settings:
    return Settings()
