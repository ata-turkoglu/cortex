import pytest

from app.providers.embeddings import EmbeddingHealth


def test_embedding_health_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        EmbeddingHealth.validate([[1.0], [1.0, 2.0]])
