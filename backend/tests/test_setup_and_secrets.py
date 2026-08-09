from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.workspaces import get_session
from app.core import secrets
from app.core.secrets import SecretStore, redact
from app.main import app
from app.models import Base, SetupState


def test_setup_completion_persists_only_safe_state():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)

    def session_override():
        session = session_local()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_session] = session_override
    try:
        response = TestClient(app).post(
            "/api/v1/settings/setup/complete", json={"data_path": "D:/Cortex Veri"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.json() == {"completed": True}
    with session_local() as session:
        stored = session.get(SetupState, 1)
        assert stored is not None
        assert "completed" in stored.state_json
        assert "api_key" not in stored.state_json


def test_secret_store_uses_keyring_and_redacts_values(monkeypatch):
    calls = []
    monkeypatch.setattr(secrets.keyring, "set_password", lambda *args: calls.append(args))
    SecretStore().set("openai", "sk-secret")
    assert calls == [("cortex", "openai", "sk-secret")]
    assert redact("sk-secret") == "[REDACTED]"


def test_secret_store_get_falls_back_when_no_os_keyring_is_available(monkeypatch):
    monkeypatch.setattr(
        secrets.keyring,
        "get_password",
        lambda *_: (_ for _ in ()).throw(secrets.KeyringError("unavailable")),
    )
    assert SecretStore().get("openai_api_key") is None


def test_secret_store_set_falls_back_when_no_os_keyring_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr(
        secrets.keyring,
        "set_password",
        lambda *_: (_ for _ in ()).throw(secrets.KeyringError("unavailable")),
    )
    monkeypatch.setenv("CORTEX_SECRET_STORE_PATH", str(tmp_path))
    SecretStore().set("openai_api_key", "sk-secret")
    assert SecretStore().get("openai_api_key") == "sk-secret"


def test_secret_store_persists_encrypted_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        secrets.keyring,
        "set_password",
        lambda *_: (_ for _ in ()).throw(secrets.KeyringError("unavailable")),
    )
    monkeypatch.setattr(
        secrets.keyring,
        "get_password",
        lambda *_: (_ for _ in ()).throw(secrets.KeyringError("unavailable")),
    )
    monkeypatch.setenv("CORTEX_SECRET_STORE_PATH", str(tmp_path))
    SecretStore().set("openai_api_key", "sk-secret")
    assert SecretStore().get("openai_api_key") == "sk-secret"
    assert "sk-secret" not in (tmp_path / "values.json").read_text()
