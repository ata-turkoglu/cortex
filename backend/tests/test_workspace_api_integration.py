from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.workspaces import get_session
from app.main import app
from app.models import Base


def test_workspace_api_creates_its_isolated_resource_records():
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
            "/api/v1/workspaces",
            json={"name": "Integration", "slug": "integration"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "integration"
