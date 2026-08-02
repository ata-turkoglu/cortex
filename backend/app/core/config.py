from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CORTEX_", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./data/sqlite/cortex.db"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    ollama_base_url: str = "http://host.docker.internal:11434"
    data_path: Path = Path("./data")
    sqlite_busy_timeout_ms: int = 5000
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
