import httpx

from ..core.config import get_settings
from .base import ModelCapability


class OllamaProvider:
    async def list_models(self) -> list[ModelCapability]:
        async with httpx.AsyncClient(timeout=5) as client:
            payload = (await client.get(get_settings().ollama_base_url + "/api/tags")).json()
        return [
            ModelCapability(
                "ollama",
                model["name"],
                chat=True,
                embeddings="embed" in model["name"] or "bge" in model["name"],
            )
            for model in payload.get("models", [])
        ]

    async def missing_embedding_command(self, model: str = "qwen3-embedding:0.6b") -> str:
        return f"ollama pull {model}"
