from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="CORTEX_", extra="ignore", validate_assignment=True
    )
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
    allowed_extensions: str = ".md,.txt,.docx,.pdf"
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_batch_size: int = 64
    embedding_min_batch_size: int = 1
    embedding_timeout_seconds: int = 60
    embedding_keep_alive: str = "5m"
    embedding_concurrency: int = 2
    dense_top_k: int = 30
    bm25_top_k: int = 30
    fusion_candidate_limit: int = 40
    reranker_input_limit: int = 30
    final_evidence_top_k: int = 10
    document_lookup_final_evidence_top_k: int = 50
    reranker_model: str | None = None
    reranker_device: str | None = None
    router_confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    router_multi_route_threshold: float = Field(default=0.8, ge=0, le=1)
    graphrag_pending_document_threshold: int = 20
    graphrag_update_mode: Literal["manual", "threshold"] = "manual"
    graphrag_max_documents_per_run: int = 500
    graphrag_cost_warning_usd: float = 0.0
    graphrag_use_batch_api: bool = False
    graphrag_provider: Literal["openai", "ollama"] = "openai"
    graphrag_model: str = "gpt-5.6-luna"
    graphrag_extraction_provider: Literal["openai", "ollama"] = "openai"
    graphrag_extraction_model: str = "gpt-4.1-mini"
    graphrag_claims_provider: Literal["openai", "ollama"] = "openai"
    graphrag_claims_model: str = "gpt-4.1-mini"
    graphrag_claims_enabled: bool = False
    graphrag_community_provider: Literal["openai", "ollama"] = "openai"
    graphrag_community_model: str = "gpt-4.1-mini"
    graphrag_local_provider: Literal["openai", "ollama"] = "openai"
    graphrag_local_model: str = "gpt-4.1"
    graphrag_global_provider: Literal["openai", "ollama"] = "openai"
    graphrag_global_model: str = "gpt-4.1"
    graphrag_drift_provider: Literal["openai", "ollama"] = "openai"
    graphrag_drift_model: str = "gpt-4.1"
    graphrag_drift_n_depth: int = Field(default=2, ge=1, le=5)
    graphrag_drift_k_followups: int = Field(default=5, ge=1, le=20)
    graphrag_drift_primer_folds: int = Field(default=3, ge=1, le=10)
    graphrag_drift_concurrency: int = Field(default=4, ge=1, le=16)
    graphrag_drift_max_llm_calls: int = Field(default=16, ge=1, le=100)
    graphrag_query_fallback_to_hybrid: bool = False
    graphrag_query_wait_seconds: int = Field(default=20, ge=1, le=60)
    workflow_ingestion_concurrency: int = 2
    workflow_dense_reindex_concurrency: int = 1
    workflow_graphrag_reindex_concurrency: int = 1
    workflow_deletion_concurrency: int = 1
    workflow_retention_days: int = 30
    workflow_retry_limit: int = 3
    workflow_retry_backoff_seconds: int = 5
    workflow_timeout_seconds: int = 900
    default_page_size: int = 50
    health_check_interval_seconds: int = 15
    sse_reconnect_interval_seconds: int = 3
    conversation_memory_window_messages: int = 12
    answer_style: Literal["concise", "balanced", "detailed"] = "balanced"
    grounding_required: bool = True
    metadata_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    metadata_model: str = "gpt-5.6-luna"
    answer_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    answer_model: str = "gpt-5.6-luna"
    router_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    router_model: str = "gpt-5.6-luna"
    summary_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    summary_model: str = "gpt-5.6-luna"
    query_expansion_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    query_expansion_model: str = "gpt-5.6-luna"
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
