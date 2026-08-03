from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    upload_max_bytes: int = 50 * 1024 * 1024
    chunk_token_limit: int = 500
    chunk_overlap_tokens: int = 50
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_batch_size: int = 64
    embedding_min_batch_size: int = 1
    dense_top_k: int = 30
    bm25_top_k: int = 30
    fusion_candidate_limit: int = 40
    reranker_input_limit: int = 30
    final_evidence_top_k: int = 10
    reranker_model: str | None = None
    reranker_device: str | None = None
    graphrag_pending_document_threshold: int = 20
    graphrag_update_mode: Literal["manual", "threshold"] = "manual"
    graphrag_max_documents_per_run: int = 500
    graphrag_cost_warning_usd: float = 0.0
    graphrag_use_batch_api: bool = False
    workflow_ingestion_concurrency: int = 2
    workflow_dense_reindex_concurrency: int = 1
    workflow_graphrag_reindex_concurrency: int = 1
    workflow_deletion_concurrency: int = 1
    workflow_retention_days: int = 30
    conversation_memory_window_messages: int = 12
    answer_style: Literal["concise", "balanced", "detailed"] = "balanced"
    query_expansion_enabled: bool = False
    automatic_quality_escalation_enabled: bool = False
    daily_soft_budget_usd: float = 0.0
    monthly_soft_budget_usd: float = 0.0
    budget_warning_percent: int = 80
    openai_input_cost_per_1k_usd: float = 0.0
    openai_output_cost_per_1k_usd: float = 0.0
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
