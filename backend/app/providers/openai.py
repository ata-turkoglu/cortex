import httpx

from ..core.config import get_settings
from ..core.secrets import SecretStore
from .base import GeneratedText, ModelCapability


class OpenAIProvider:
    def configured(self) -> bool:
        return bool(get_settings().openai_api_key or SecretStore().get("openai_api_key"))

    async def list_models(self) -> list[ModelCapability]:
        return [
            ModelCapability("openai", "gpt-5.6-luna", chat=True),
            ModelCapability("openai", "text-embedding-3-small", embeddings=True),
        ]

    async def generate(self, model: str, instructions: str, input_text: str) -> GeneratedText:
        """Call Responses outside database transactions through a worker-owned adapter."""
        api_key = get_settings().openai_api_key or SecretStore().get("openai_api_key")
        if not api_key:
            raise RuntimeError("OpenAI is not configured")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "instructions": instructions, "input": input_text},
            )
            response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        return GeneratedText(
            text=str(payload.get("output_text") or ""),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
