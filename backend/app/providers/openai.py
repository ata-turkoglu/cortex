from ..core.config import get_settings
from .base import ModelCapability


class OpenAIProvider:
    def configured(self) -> bool:
        return bool(get_settings().openai_api_key)

    async def list_models(self) -> list[ModelCapability]:
        return [
            ModelCapability("openai", "gpt-5.6-luna", chat=True),
            ModelCapability("openai", "text-embedding-3-small", embeddings=True),
        ]
