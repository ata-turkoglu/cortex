from fastapi.testclient import TestClient

from app.main import app


def test_provider_status_never_returns_secret():
    body = TestClient(app).get("/api/v1/settings/providers").json()
    assert "openai_api_key" not in str(body)
    assert body["providers"][0]["configured"] is False
