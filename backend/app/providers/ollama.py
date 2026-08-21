import httpx

from ..core.config import get_settings
from .base import GeneratedText, ModelCapability


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
                digest=model.get("digest"),
            )
            for model in payload.get("models", [])
        ]

    async def missing_embedding_command(self, model: str = "qwen3-embedding:0.6b") -> str:
        return f"ollama pull {model}"

    async def generate(self, model: str, instructions: str, input_text: str) -> GeneratedText:
        """Generate JSON-capable text through the local Ollama chat API."""
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                get_settings().ollama_base_url + "/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {"temperature": 0, "num_predict": 2048},
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": input_text},
                    ],
                },
            )
            response.raise_for_status()
        payload = response.json()
        message = payload.get("message") or {}
        input_tokens = payload.get("prompt_eval_count")
        output_tokens = payload.get("eval_count")
        return GeneratedText(
            text=str(message.get("content") or ""),
            input_tokens=int(input_tokens) if input_tokens is not None else None,
            output_tokens=int(output_tokens) if output_tokens is not None else None,
            total_tokens=(
                int(input_tokens) + int(output_tokens)
                if input_tokens is not None and output_tokens is not None
                else None
            ),
            request_id=str(payload.get("created_at") or "ollama-local"),
        )
