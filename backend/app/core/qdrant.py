"""Configured Qdrant client factory; retrieval owns all workspace-scoped operations."""

from functools import lru_cache

from httpx import Timeout
from qdrant_client import QdrantClient

from .config import get_settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    client = QdrantClient(url=get_settings().qdrant_url, timeout=None)

    # qdrant-client 1.13.2 treats ``timeout=None`` as "do not pass a timeout"
    # and httpx then restores its five-second default. GraphRAG artifact mirroring
    # can legitimately take longer than that while Qdrant creates a collection or
    # persists a large batch, so disable all HTTP deadlines explicitly.
    client._client.openapi_client.client._client.timeout = Timeout(None)  # type: ignore[attr-defined]
    return client
