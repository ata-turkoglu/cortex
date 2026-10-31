import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.settings_service import load_runtime_settings, save_settings
from app.main import app
from app.models import GlobalSettings
from app.providers.base import ModelCapability


def test_provider_status_never_returns_secret(monkeypatch):
    monkeypatch.setattr("app.api.settings.OpenAIProvider.configured", lambda _self: False)
    body = TestClient(app).get("/api/v1/settings/providers").json()
    assert "openai_api_key" not in str(body)
    assert body["providers"][0]["configured"] is False


def test_runtime_settings_never_return_neo4j_credentials():
    engine = create_engine("sqlite:///:memory:")
    GlobalSettings.__table__.create(engine)
    with Session(engine) as session:
        session.add(
            GlobalSettings(
                key="runtime",
                value_json=json.dumps(
                    {"embedding_provider": "ollama", "embedding_model": "bge-m3:latest"}
                ),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
        values = load_runtime_settings(session)
    assert "neo4j_password" not in values
    assert "neo4j_uri" not in values


def test_ollama_model_pull_rejects_an_invalid_model_name():
    response = TestClient(app).post(
        "/api/v1/settings/ollama/models/pull", json={"model": "bad model!"}
    )
    assert response.status_code == 422


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


def test_semantic_planner_tiers_require_available_openai_chat_models(monkeypatch):
    async def capabilities():
        return {
            "openai": [ModelCapability("openai", "planner-model", chat=True)],
            "anthropic": [],
            "ollama": [],
        }

    monkeypatch.setattr("app.api.settings._capabilities", capabilities)
    monkeypatch.setattr("app.api.settings.OpenAIProvider.configured", lambda _self: True)
    original = {
        f"semantic_planner_{tier}_{field}": getattr(
            get_settings(), f"semantic_planner_{tier}_{field}"
        )
        for tier in ("simple", "standard", "complex")
        for field in ("provider", "model")
    }
    try:
        for tier in ("simple", "standard", "complex"):
            setattr(get_settings(), f"semantic_planner_{tier}_provider", "openai")
            setattr(get_settings(), f"semantic_planner_{tier}_model", "planner-model")
        from app.api.settings import _validate_assignments

        asyncio.run(_validate_assignments({}))
        with pytest.raises(HTTPException, match="Semantic Planner / Standard"):
            asyncio.run(_validate_assignments({"semantic_planner_standard_model": "invalid"}))
    finally:
        for field, value in original.items():
            setattr(get_settings(), field, value)
