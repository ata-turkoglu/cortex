"""The single production boundary for durable embedding configuration."""

from sqlalchemy.orm import Session

from ..providers.base import EmbeddingProvider
from ..providers.embeddings import (
    EmbeddingConfiguration,
    OllamaEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    Qwen3EmbeddingAdapter,
)
from .settings_service import RuntimeEmbeddingConfigurationError, load_runtime_settings


def load_production_embedding_configuration(session: Session) -> EmbeddingConfiguration:
    """Resolve only the durable provider/model assignment; never infer a model."""
    values = load_runtime_settings(session)
    provider = values.get("embedding_provider")
    model = values.get("embedding_model")
    if not isinstance(provider, str) or not isinstance(model, str):
        raise RuntimeEmbeddingConfigurationError(
            "persisted runtime embedding provider/model is missing or invalid"
        )
    return EmbeddingConfiguration(provider=provider, model=model)


def build_production_embedder(session: Session) -> tuple[EmbeddingConfiguration, EmbeddingProvider]:
    """Build the configured adapter after strictly loading the durable setting row."""
    configuration = load_production_embedding_configuration(session)
    if configuration.provider == "ollama":
        provider: EmbeddingProvider = (
            Qwen3EmbeddingAdapter(configuration)
            if configuration.model.startswith("qwen3")
            else OllamaEmbeddingAdapter(configuration)
        )
    elif configuration.provider == "openai":
        provider = OpenAIEmbeddingAdapter(configuration)
    else:  # EmbeddingConfiguration validates this too; retain a clear production error.
        raise RuntimeEmbeddingConfigurationError("unsupported persisted embedding provider")
    return configuration, provider
