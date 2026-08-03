from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.settings_service import load_runtime_settings, save_settings
from app.main import app
from app.models import GlobalSettings


def test_provider_status_never_returns_secret():
    body = TestClient(app).get("/api/v1/settings/providers").json()
    assert "openai_api_key" not in str(body)
    assert body["providers"][0]["configured"] is False


def test_global_settings_persist_and_apply_to_runtime():
    engine = create_engine("sqlite:///:memory:")
    GlobalSettings.__table__.create(engine)
    original = get_settings().workflow_retention_days
    try:
        with Session(engine) as session:
            values, reindex_required = save_settings(session, {"workflow_retention_days": 14})
            session.commit()
            assert values["workflow_retention_days"] == 14
            assert reindex_required is False
        get_settings().workflow_retention_days = original
        with Session(engine) as session:
            assert load_runtime_settings(session)["workflow_retention_days"] == 14
    finally:
        get_settings().workflow_retention_days = original
