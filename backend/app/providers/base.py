from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelCapability:
    provider: str
    model: str
    chat: bool = False
    embeddings: bool = False


class LLMProvider(Protocol):
    async def list_models(self) -> list[ModelCapability]: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
