import hashlib
import json
import math
from dataclasses import dataclass

import httpx

from ..core.config import get_settings
from .base import EmbeddingProvider


class EmbeddingHealth:
    @staticmethod
    def validate(vectors: list[list[float]]) -> int:
        if not vectors or not vectors[0]:
            raise ValueError("embedding vectors are empty")
        dimension = len(vectors[0])
        if any(
            len(vector) != dimension or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("embedding dimensions or values are invalid")
        return dimension


@dataclass(frozen=True)
class EmbeddingHealthResult:
    provider: str
    model: str
    dimension: int


async def checked_embed(provider: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    vectors = await provider.embed(texts)
    EmbeddingHealth.validate(vectors)
    return vectors


async def adaptive_embed(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    batch_size: int,
    min_batch_size: int = 1,
) -> list[list[float]]:
    """Retry a failed batch at smaller sizes without reordering multilingual input."""
    if batch_size < 1 or min_batch_size < 1 or min_batch_size > batch_size:
        raise ValueError("invalid embedding batch limits")
    vectors: list[list[float]] = []
    position = 0
    current_batch_size = batch_size
    while position < len(texts):
        batch = texts[position : position + current_batch_size]
        try:
            vectors.extend(await checked_embed(provider, batch))
            position += len(batch)
        except Exception:
            if current_batch_size == min_batch_size:
                raise
            current_batch_size = max(min_batch_size, current_batch_size // 2)
    return vectors


@dataclass(frozen=True)
class EmbeddingConfiguration:
    provider: str
    model: str
    dimension: int | None = None
    model_digest: str | None = None
    normalized: bool = True
    text_template_version: int = 1

    @property
    def fingerprint(self) -> str:
        payload = {
            "dimension": self.dimension,
            "model": self.model,
            "model_digest": self.model_digest,
            "normalized": self.normalized,
            "provider": self.provider,
            "text_template_version": self.text_template_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def prepare_embedding_text(content: str, *, title: str, heading: str | None = None) -> str:
    """Stable multilingual document template; never lowercase or normalize Unicode."""
    sections = [f"Title: {title}"]
    if heading:
        sections.append(f"Heading: {heading}")
    sections.append(f"Content: {content}")
    return "\n".join(sections)


def prepared_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class OllamaEmbeddingAdapter:
    """Ollama's embedding endpoint isolated from retrieval services."""

    def __init__(
        self,
        configuration: EmbeddingConfiguration | None = None,
        *,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.configuration = configuration or EmbeddingConfiguration(
            settings.embedding_provider, settings.embedding_model
        )
        self.base_url = base_url or settings.ollama_base_url
        self.transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # A local cold load may take longer than a normal HTTP call, but an
        # unbounded wait leaves the durable workflow permanently `running`.
        # The global operational timeout keeps failure visible and retryable.
        async with httpx.AsyncClient(
            timeout=get_settings().embedding_timeout_seconds, transport=self.transport
        ) as client:
            response = await client.post(
                self.base_url + "/api/embed",
                json={"model": self.configuration.model, "input": texts},
            )
            response.raise_for_status()
        vectors = response.json().get("embeddings", [])
        EmbeddingHealth.validate(vectors)
        return vectors

    async def health_check(self) -> EmbeddingHealthResult:
        dimension = EmbeddingHealth.validate(
            await self.embed(["Cortex embedding health check: İstanbul"])
        )
        return EmbeddingHealthResult(
            provider=self.configuration.provider,
            model=self.configuration.model,
            dimension=dimension,
        )


class OpenAIEmbeddingAdapter:
    """OpenAI embeddings boundary; network calls remain worker-owned."""

    def __init__(
        self, model: str = "text-embedding-3-small", *, api_key: str | None = None
    ) -> None:
        from ..core.secrets import SecretStore

        self.model = model
        self.api_key = (
            api_key or get_settings().openai_api_key or SecretStore().get("openai_api_key")
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OpenAI is not configured")
        async with httpx.AsyncClient(timeout=get_settings().embedding_timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
        vectors = [item["embedding"] for item in response.json().get("data", [])]
        EmbeddingHealth.validate(vectors)
        return vectors


class Qwen3EmbeddingAdapter(OllamaEmbeddingAdapter):
    """Qwen3 policy stays here, not in retrieval feature code."""

    def prepare_query(self, query: str) -> str:
        return "Query: " + query.replace("\r\n", "\n").replace("\r", "\n")

    def prepare_document(self, content: str, *, title: str, heading: str | None = None) -> str:
        return prepare_embedding_text(
            content.replace("\r\n", "\n").replace("\r", "\n"),
            title=title,
            heading=heading,
        )
