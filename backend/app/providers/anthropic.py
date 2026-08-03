from ..core.config import get_settings
from ..core.secrets import SecretStore
from .base import ModelCapability


class AnthropicProvider:
    def configured(self) -> bool:
        return bool(get_settings().anthropic_api_key or SecretStore().get("anthropic_api_key"))

    async def list_models(self) -> list[ModelCapability]:
        return [ModelCapability("anthropic", "configured-by-user", chat=True)]
