import httpx

from ..core.config import get_settings
from ..core.secrets import SecretStore
from .base import GeneratedText, ModelCapability

_NON_TEXT_MODEL_MARKERS = (
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "audio",
    "image",
    "realtime",
    "transcribe",
    "search-preview",
)


def _capability(model: str) -> ModelCapability | None:
    normalized = model.lower()
    if "embedding" in normalized:
        return ModelCapability("openai", model, embeddings=True)
    if any(marker in normalized for marker in _NON_TEXT_MODEL_MARKERS):
        return None
    if normalized.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4")):
        return ModelCapability("openai", model, chat=True)
    return None


class OpenAIProvider:
    def configured(self) -> bool:
        return bool(get_settings().openai_api_key or SecretStore().get("openai_api_key"))

    async def list_models(self) -> list[ModelCapability]:
        api_key = get_settings().openai_api_key or SecretStore().get("openai_api_key")
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            models = []
            for item in response.json().get("data", []):
                model_id = item.get("id")
                if isinstance(model_id, str):
                    capability = _capability(model_id)
                    if capability:
                        models.append(capability)
            return sorted(models, key=lambda item: item.model)
        except (httpx.HTTPError, ValueError, TypeError):
            return []

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
