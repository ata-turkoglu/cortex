from types import SimpleNamespace

from httpx import Timeout
from qdrant_client import QdrantClient

from app.core.qdrant import get_qdrant_client


def test_qdrant_client_has_no_http_deadline(monkeypatch):
    client = QdrantClient(url="http://example.invalid", check_compatibility=False)
    received: dict[str, object] = {}

    def create_client(**kwargs):
        received.update(kwargs)
        return client

    monkeypatch.setattr("app.core.qdrant.QdrantClient", create_client)
    monkeypatch.setattr(
        "app.core.qdrant.get_settings", lambda: SimpleNamespace(qdrant_url="http://example.invalid")
    )
    get_qdrant_client.cache_clear()

    configured_client = get_qdrant_client()
    timeout = configured_client._client.openapi_client.client._client.timeout

    assert timeout == Timeout(None)
    assert received == {"url": "http://example.invalid", "timeout": None}
    get_qdrant_client.cache_clear()
