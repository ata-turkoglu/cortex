from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelCapability:
    provider: str
    model: str
    chat: bool = False
    embeddings: bool = False
    digest: str | None = None


class LLMProvider(Protocol):
    async def list_models(self) -> list[ModelCapability]: ...

    async def generate(self, model: str, instructions: str, input_text: str) -> "GeneratedText": ...


@dataclass(frozen=True)
class GeneratedText:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    request_id: str | None = None
    usage_payload: dict[str, object] | None = None


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
