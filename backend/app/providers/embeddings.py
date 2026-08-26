import asyncio
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

    def __post_init__(self) -> None:
        if self.provider not in {"ollama", "openai"} or not self.model.strip():
            raise ValueError(
                "embedding configuration requires an explicit supported provider and model"
            )

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
        configuration: EmbeddingConfiguration,
        *,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        if configuration.provider != "ollama" or not configuration.model:
            raise ValueError("Ollama embedding adapter requires an explicit Ollama configuration")
        self.configuration = configuration
        self.base_url = base_url or settings.ollama_base_url
        self.transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.transport is None and "localhost" in self.base_url:
            vectors = await asyncio.to_thread(
                _native_ollama_embeddings,
                self.base_url,
                self.configuration.model,
                texts,
                get_settings().embedding_timeout_seconds,
            )
            EmbeddingHealth.validate(vectors)
            return vectors
        # A local cold load may take longer than a normal HTTP call, but an
        # unbounded wait leaves the durable workflow permanently `running`.
        # The global operational timeout keeps failure visible and retryable.
        async with httpx.AsyncClient(
            timeout=get_settings().embedding_timeout_seconds,
            transport=self.transport,
            # A local Ollama endpoint must not be sent through a process-level
            # HTTP proxy, which can return a misleading 404 for local routes.
            trust_env=False,
        ) as client:
            response = await client.post(
                self.base_url + "/api/embed",
                json={"model": self.configuration.model, "input": texts},
            )
            if response.status_code == 404:
                # The Windows host relay can reject async connections while its
                # synchronous HTTP path serves the same native batch endpoint.
                vectors = await asyncio.to_thread(
                    _native_ollama_embeddings,
                    self.base_url,
                    self.configuration.model,
                    texts,
                    get_settings().embedding_timeout_seconds,
                )
            else:
                response.raise_for_status()
                vectors = response.json().get("embeddings", [])
        EmbeddingHealth.validate(vectors)
        return vectors

    async def health_check(self) -> EmbeddingHealthResult:
        return await embedding_health_check(self)


def _native_ollama_embeddings(
    base_url: str, model: str, texts: list[str], timeout: int
) -> list[list[float]]:
    """Use the native batch endpoint through the Windows host relay."""
    # The host's IPv6 localhost relay can point at a stale endpoint while its
    # IPv4 relay serves the configured Ollama instance.
    endpoint = base_url.replace("localhost", "127.0.0.1")
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.post(
            endpoint + "/api/embed", json={"model": model, "input": texts}
        )
        response.raise_for_status()
    return response.json().get("embeddings", [])


async def embedding_health_check(adapter: OllamaEmbeddingAdapter) -> EmbeddingHealthResult:
    dimension = EmbeddingHealth.validate(
        await adapter.embed(["Cortex embedding health check: İstanbul"])
    )
    return EmbeddingHealthResult(
        adapter.configuration.provider, adapter.configuration.model, dimension
    )


class OpenAIEmbeddingAdapter:
    """OpenAI embeddings boundary; network calls remain worker-owned."""

    def __init__(
        self, configuration: EmbeddingConfiguration, *, api_key: str | None = None
    ) -> None:
        from ..core.secrets import SecretStore

        if configuration.provider != "openai":
            raise ValueError("OpenAI embedding adapter requires an explicit OpenAI configuration")
        self.configuration = configuration
        self.model = configuration.model
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
