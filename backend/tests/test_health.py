from fastapi.testclient import TestClient

from app.main import app


def test_health_has_service_map():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert "sqlite" in response.json()["services"]
