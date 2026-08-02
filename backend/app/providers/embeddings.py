import math

from .base import EmbeddingProvider


class EmbeddingHealth:
    @staticmethod
    def validate(vectors: list[list[float]]) -> int:
        if not vectors or not vectors[0]:
            raise ValueError("embedding vectors are empty")
        dimension = len(vectors[0])
        if any(
            len(vector) != dimension or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("embedding dimensions or values are invalid")
        return dimension


async def checked_embed(provider: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    vectors = await provider.embed(texts)
    EmbeddingHealth.validate(vectors)
    return vectors
