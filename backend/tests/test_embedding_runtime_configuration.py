import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.embedding_runtime import load_production_embedding_configuration
from app.core.settings_service import RuntimeEmbeddingConfigurationError
from app.models import Base, GlobalSettings
from app.providers.embeddings import EmbeddingConfiguration


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _persist(session, values: dict[str, object]) -> None:
    session.add(
        GlobalSettings(
            key="runtime",
            value_json=json.dumps(values),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_missing_runtime_embedding_configuration_fails_closed():
    with pytest.raises(RuntimeEmbeddingConfigurationError):
        load_production_embedding_configuration(_session())


@pytest.mark.parametrize(
    "values", [{"embedding_model": "bge-m3:latest"}, {"embedding_provider": "ollama"}]
)
def test_partial_runtime_embedding_configuration_fails_closed(values):
    session = _session()
    _persist(session, values)
    with pytest.raises(RuntimeEmbeddingConfigurationError):
        load_production_embedding_configuration(session)


def test_persisted_bge_configuration_is_exact_and_fingerprint_is_deterministic():
    session = _session()
    _persist(
        session,
        {"embedding_provider": "ollama", "embedding_model": "bge-m3:latest"},
    )
    configuration = load_production_embedding_configuration(session)
    assert configuration == EmbeddingConfiguration("ollama", "bge-m3:latest")
    assert EmbeddingConfiguration("ollama", "bge-m3:latest", dimension=1024).fingerprint == (
        EmbeddingConfiguration("ollama", "bge-m3:latest", dimension=1024).fingerprint
    )


def test_empty_configuration_cannot_construct_a_fingerprint():
    with pytest.raises(ValueError):
        EmbeddingConfiguration("ollama", "")
