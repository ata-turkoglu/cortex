import asyncio

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app, handled_http_exception


def test_openapi_and_error_contract_are_exposed():
    client = TestClient(app)
    schema = client.get("/api/v1/openapi.json").json()
    assert schema["info"]["title"] == "Cortex API"
    assert "/api/v1/health" in schema["paths"]


def test_client_and_validation_errors_use_the_standard_envelope():
    client = TestClient(app)
    invalid = client.post("/api/v1/workspaces", json={})
    body = invalid.json()
    assert body["code"] == "validation_error"
    assert body["message"]
    assert body["correlation_id"] == invalid.headers["X-Correlation-ID"]
    assert body["details_available"] is False

    request = Request({"type": "http", "headers": [], "state": {"correlation_id": "test-id"}})
    response = asyncio.run(handled_http_exception(request, HTTPException(404, "not found")))
    assert response.status_code == 404
    assert b'"code":"request_error"' in response.body
    assert b'"correlation_id":"test-id"' in response.body
