"""Detached V2 query embedding bound to one immutable generation scope."""

from __future__ import annotations

from typing import Protocol

from ..providers.embeddings import EmbeddingConfiguration, EmbeddingHealth, Qwen3EmbeddingAdapter
from .scope import GenerationScope


class V2QueryEmbedder(Protocol):
    async def embed(self, query: str, scope: GenerationScope) -> list[float]: ...


class ConfiguredV2QueryEmbedder:
    def __init__(self, provider, configuration: EmbeddingConfiguration) -> None:
        self.provider = provider
        self.configuration = configuration

    async def embed(self, query: str, scope: GenerationScope) -> list[float]:
        text = (
            self.provider.prepare_query(query)
            if isinstance(self.provider, Qwen3EmbeddingAdapter)
            else query
        )
        vectors = await self.provider.embed([text])
        dimension = EmbeddingHealth.validate(vectors)
        configuration = EmbeddingConfiguration(
            self.configuration.provider,
            self.configuration.model,
            dimension,
            self.configuration.model_digest,
            self.configuration.normalized,
            self.configuration.text_template_version,
        )
        if configuration.fingerprint != scope.embedding_config_hash:
            raise ValueError("GENERATION_EMBEDDING_FINGERPRINT_MISMATCH")
        return vectors[0]
