import asyncio
import sqlite3

import redis.asyncio as redis
from fastapi import APIRouter

from ..core.config import get_settings

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


@router.get("/health")
async def health():
    settings = get_settings()
    sqlite_status = "healthy"
    try:
        sqlite3.connect(settings.database_url.removeprefix("sqlite:///"), timeout=1).close()
    except sqlite3.Error:
        sqlite_status = "unavailable"
    redis_status, qdrant, ollama = await asyncio.gather(
        probe_redis(settings.redis_url),
        probe(settings.qdrant_url + "/healthz"),
        probe(settings.ollama_base_url + "/api/tags"),
    )
    return {
        "status": "healthy" if sqlite_status == redis_status == qdrant == "healthy" else "degraded",
        "services": {
            "backend": "healthy",
            "sqlite": sqlite_status,
            "redis": redis_status,
            "qdrant": qdrant,
            "ollama": ollama,
            "worker": "healthy" if redis_status == "healthy" else "unknown",
            "openai": "not-configured",
            "anthropic": "not-configured",
            "graphrag": "not-installed",
        },
    }
