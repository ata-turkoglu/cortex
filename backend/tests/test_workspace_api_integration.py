from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.workspaces import get_session
from app.main import app
from app.models import Base


def enable_foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")


def test_workspace_api_creates_its_isolated_resource_records():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", enable_foreign_keys)
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
            "/api/v1/workspaces",
            json={"name": "Integration", "slug": "integration"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "integration"


def test_catalogue_endpoints_are_workspace_scoped():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", enable_foreign_keys)
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
        client = TestClient(app)
        workspace = client.post(
            "/api/v1/workspaces", json={"name": "Catalogue", "slug": "catalogue"}
        ).json()
        overview = client.get("/api/v1/overview")
        workspace_overview = client.get(f"/api/v1/workspaces/{workspace['id']}/overview")
        documents = client.get(f"/api/v1/workspaces/{workspace['id']}/documents")
    finally:
        app.dependency_overrides.clear()

    assert overview.status_code == 200
    assert overview.json()["workspace_count"] == 1
    assert workspace_overview.json()["document_count"] == 0
    assert documents.json() == []
