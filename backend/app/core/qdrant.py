"""Configured Qdrant client factory; retrieval owns all workspace-scoped operations."""
from functools import lru_cache

from qdrant_client import QdrantClient

from .config import get_settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, timeout=2)
