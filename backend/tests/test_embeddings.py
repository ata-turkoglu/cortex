import asyncio
import json

import httpx
import pytest

from app.core.config import get_settings
from app.providers.embeddings import (
    EmbeddingConfiguration,
    EmbeddingHealth,
    OllamaEmbeddingAdapter,
    Qwen3EmbeddingAdapter,
    adaptive_embed,
)
from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore


def test_embedding_health_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        EmbeddingHealth.validate([[1.0], [1.0, 2.0]])


def test_adaptive_embedding_retries_with_smaller_batches_in_order():
    class LimitedProvider:
        async def embed(self, texts):
            if len(texts) > 1:
                raise RuntimeError("batch too large")
            return [[float(len(texts[0]))]]

    vectors = asyncio.run(adaptive_embed(LimitedProvider(), ["a", "bb", "ccc"], batch_size=4))
    assert vectors == [[1.0], [2.0], [3.0]]


def test_ollama_embedding_health_check_uses_embed_endpoint_without_a_real_model():
    import httpx

    def handler(request):
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {
            "model": "qwen3-embedding:0.6b",
            "input": ["Cortex embedding health check: İstanbul"],
            "keep_alive": get_settings().embedding_keep_alive,
        }
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    adapter = OllamaEmbeddingAdapter(
        EmbeddingConfiguration("ollama", "qwen3-embedding:0.6b"),
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(adapter.health_check())
    assert (result.provider, result.model, result.dimension) == (
        "ollama",
        "qwen3-embedding:0.6b",
        3,
    )


def test_ollama_embedding_requests_use_the_global_timeout(monkeypatch):
    import httpx

    received: dict[str, object] = {}
    original_client = httpx.AsyncClient

    def create_client(*args, **kwargs):
        received.update(kwargs)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.providers.embeddings.httpx.AsyncClient", create_client)
    adapter = OllamaEmbeddingAdapter(
        EmbeddingConfiguration("ollama", "bge-m3:latest"),
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})
        ),
    )

    assert asyncio.run(adapter.embed(["test"])) == [[1.0, 0.0]]
    assert received["timeout"] == 60


def test_qwen_adapter_prepares_turkish_query_and_document_without_unicode_loss():
    adapter = Qwen3EmbeddingAdapter(EmbeddingConfiguration("ollama", "qwen3-embedding:0.6b"))
    assert adapter.prepare_query("İstanbul\r\nşeker") == "Query: İstanbul\nşeker"
    prepared = adapter.prepare_document("ığdır", title="Başlık", heading="Özet")
    assert "Başlık" in prepared
    assert "ığdır" in prepared


def test_turkish_and_cross_lingual_dense_retrieval_smoke():
    import httpx
    from qdrant_client import QdrantClient

    adapter = Qwen3EmbeddingAdapter(
        EmbeddingConfiguration("ollama", "qwen3-embedding:0.6b", dimension=2),
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"embeddings": [[1.0, 0.0] for _ in json.loads(request.content)["input"]]},
            )
        ),
    )
    document = adapter.prepare_document("Ankara Türkiye'nin başkentidir.", title="Coğrafya")
    query = adapter.prepare_query("What is the capital of Turkey?")
    document_vector, query_vector = asyncio.run(adapter.embed([document, query]))
    store = WorkspaceQdrantStore(
        QdrantClient(":memory:"),
        "workspace-a",
        embedding_config_hash=adapter.configuration.fingerprint,
    )
    store.upsert(
        "chunks",
        [VectorRecord("ankara", document_vector, {"content": "Ankara Türkiye'nin başkentidir."})],
        dimension=2,
    )
    assert store.search("chunks", query_vector, 1)[0].content.startswith("Ankara")


def test_optional_bge_m3_embedding_compatibility_uses_the_same_ollama_contract():
    import httpx

    adapter = OllamaEmbeddingAdapter(
        EmbeddingConfiguration("ollama", "bge-m3:567m", dimension=3),
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"embeddings": [[1, 0, 0]]})
        ),
    )
    result = asyncio.run(adapter.health_check())
    assert (result.model, result.dimension) == ("bge-m3:567m", 3)


def test_concurrent_embedding_runs_batches_in_parallel_and_keeps_input_order():
    class TrackingProvider:
        def __init__(self):
            self.in_flight = 0
            self.peak = 0

        async def embed(self, texts):
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            await asyncio.sleep(0.01)
            self.in_flight -= 1
            return [[float(len(text)), 1.0] for text in texts]

    provider = TrackingProvider()
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]

    vectors = asyncio.run(adaptive_embed(provider, texts, batch_size=2, concurrency=2))

    assert [vector[0] for vector in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert provider.peak == 2


def test_ollama_embedding_requests_send_the_configured_keep_alive(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_keep_alive", "30m")

    def handler(request):
        assert json.loads(request.content)["keep_alive"] == "30m"
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    adapter = OllamaEmbeddingAdapter(
        EmbeddingConfiguration("ollama", "bge-m3"),
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(adapter.embed(["metin"])) == [[1.0, 0.0]]
