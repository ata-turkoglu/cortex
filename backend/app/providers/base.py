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

    async def generate(self, model: str, instructions: str, input_text: str) -> "GeneratedText": ...


@dataclass(frozen=True)
class GeneratedText:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
