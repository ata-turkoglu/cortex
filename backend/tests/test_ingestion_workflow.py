from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.workflow import create_ingestion_run
from app.models import Base, WorkflowStepRun, Workspace


def test_ingestion_run_is_persisted_with_its_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="ingestion",
        name="Ingestion",
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    run = create_ingestion_run(session, workspace.id, "version-id")
    session.commit()
    assert run.job_type == "ingestion"
    assert run.state == "completed"
    assert [step.step_name for step in session.query(WorkflowStepRun).all()] == [
        "parse",
        "normalize",
        "logical_documents",
        "chunk",
        "index",
    ]
    assert all(step.state == "completed" for step in session.query(WorkflowStepRun).all())


def test_queued_ingestion_run_starts_with_durable_pending_steps():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()), slug="queued-ingestion", name="Queued ingestion", state="active",
        created_at=now, updated_at=now,
    )
    session.add(workspace)
    run = create_ingestion_run(session, workspace.id, "version-id", queued=True)
    session.commit()
    steps = session.query(WorkflowStepRun).filter_by(workflow_run_id=run.id).all()
    assert run.state == "queued"
    assert [step.state for step in steps] == ["pending"] * 5
