from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.workspaces import get_session
from app.core import database
from app.main import app
from app.models import Base, WorkflowRun
from app.workflows.service import execute_run


def test_sse_reconnect_restores_terminal_workflow_state():
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

    original_session_local = database.SessionLocal
    database.SessionLocal = session_local
    app.dependency_overrides[get_session] = session_override
    try:
        client = TestClient(app)
        workspace = client.post(
            "/api/v1/workspaces", json={"name": "SSE", "slug": "sse"}
        ).json()
        created = client.post(
            "/api/v1/workflows",
            json={"workspace_id": workspace["id"], "job_type": "ingestion", "payload": {}},
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]
        session = session_local()
        execute_run(session, run_id)
        session.commit()
        assert session.get(WorkflowRun, run_id).state == "completed"
        session.close()

        first = client.get(f"/api/v1/workflows/{run_id}/events")
        assert first.status_code == 200
        event_ids = [
            line.removeprefix("id: ") for line in first.text.splitlines() if line.startswith("id: ")
        ]
        assert event_ids
        reconnected = client.get(
            f"/api/v1/workflows/{run_id}/events",
            headers={"Last-Event-ID": event_ids[-1]},
        )
        assert "event: state" in reconnected.text
        assert '"state": "completed"' in reconnected.text
    finally:
        database.SessionLocal = original_session_local
        app.dependency_overrides.clear()
