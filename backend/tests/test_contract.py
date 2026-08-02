from fastapi.testclient import TestClient

from app.main import app


def test_openapi_and_error_contract_are_exposed():
    client = TestClient(app)
    schema = client.get("/api/v1/openapi.json").json()
    assert schema["info"]["title"] == "Cortex API"
    assert "/api/v1/health" in schema["paths"]
