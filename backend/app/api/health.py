import asyncio
import importlib.util
import sqlite3

import redis.asyncio as redis
from fastapi import APIRouter

from ..core.config import get_settings
from ..core.qdrant import get_qdrant_client
from ..knowledge.graph import Neo4jConfigurationError, Neo4jGraphAdapter
from ..providers.anthropic import AnthropicProvider
from ..providers.openai import OpenAIProvider

router = APIRouter(tags=["health"])


async def probe(url: str) -> str:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.get(url)
            return "healthy"
    except httpx.HTTPError:
        return "unavailable"


async def probe_redis(url: str) -> str:
    client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
    try:
        await client.ping()
        return "healthy"
    except redis.RedisError:
        return "unavailable"
    finally:
        await client.aclose()


async def probe_qdrant() -> str:
    try:
        await asyncio.to_thread(get_qdrant_client().get_collections)
        return "healthy"
    except Exception:
        return "unavailable"


def _probe_neo4j_sync() -> str:
    try:
        with Neo4jGraphAdapter.from_settings("health") as adapter:
            adapter.verify_connectivity()
        return "healthy"
    except Neo4jConfigurationError:
        return "not-configured"
    except Exception:
        return "unavailable"


async def probe_neo4j() -> str:
    return await asyncio.to_thread(_probe_neo4j_sync)


@router.get("/health")
async def health():
    settings = get_settings()
    sqlite_status = "healthy"
    try:
        sqlite3.connect(settings.database_url.removeprefix("sqlite:///"), timeout=1).close()
    except sqlite3.Error:
        sqlite_status = "unavailable"
    redis_status, qdrant, neo4j, ollama = await asyncio.gather(
        probe_redis(settings.redis_url),
        probe_qdrant(),
        probe_neo4j(),
        probe(settings.ollama_base_url + "/api/tags"),
    )
    services = {
        "backend": "healthy",
        "sqlite": sqlite_status,
        "redis": redis_status,
        "qdrant": qdrant,
        "neo4j": neo4j,
        "ollama": ollama,
        "worker": "healthy" if redis_status == "healthy" else "unknown",
        "openai": "configured" if OpenAIProvider().configured() else "not-configured",
        "anthropic": "configured" if AnthropicProvider().configured() else "not-configured",
        "graphrag": "available" if importlib.util.find_spec("graphrag") else "not-installed",
    }
    return {
        "status": (
            "healthy"
            if sqlite_status == redis_status == qdrant == neo4j == "healthy"
            else "degraded"
        ),
        "services": services,
        "components": [
            {"id": name, "label": name.replace("_", " ").title(), "status": status}
            for name, status in services.items()
        ],
    }
