from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    Document,
    QueryStepRun,
    WorkflowEvent,
    WorkflowRun,
    Workspace,
    WorkspaceLock,
)
from app.workflows.queries import create_query_run
from app.workflows.service import (
    cleanup_retention,
    create_run,
    execute_run,
    recover_stale,
    redact_exception,
    request_cancel,
    retry_from_failed_step,
    schedule_orphan_reconciliation,
)


def session_with_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug="workflows",
        name="Workflows",
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    session.commit()
    return session, workspace.id


def test_workflow_steps_events_and_workspace_lock_are_durable():
    session, workspace_id = session_with_workspace()
    run = create_run(session, workspace_id, "dense_reindex")
    session.commit()
    execute_run(session, run.id)
    session.commit()
    assert run.state == "completed"
    assert not session.query(WorkspaceLock).all()
    assert len(session.query(WorkflowEvent).all()) >= 2


def test_cancellation_and_restart_recovery_are_visible():
    session, workspace_id = session_with_workspace()
    run = create_run(session, workspace_id, "ingestion")
    request_cancel(session, run)
    execute_run(session, run.id)
    assert run.state == "cancelled"
    run.state = "running"
    assert recover_stale(session) == 1
    assert run.state == "interrupted"
    assert run.recovery_state == "restart_detected"
    retry_from_failed_step(session, run)
    assert run.state == "queued"


def test_concurrency_blocks_conflicting_stage_and_retention_soft_deletes_history():
    session, workspace_id = session_with_workspace()
    first = create_run(session, workspace_id, "dense_reindex")
    second = create_run(session, str(uuid4()), "dense_reindex")
    first.state = "running"
    execute_run(session, second.id)
    assert second.state == "queued"
    first.state = "completed"
    first.finished_at = datetime.now(UTC) - timedelta(days=31)
    assert cleanup_retention(session) == 1
    assert first.deleted_at is not None


def test_document_deletion_workflow_is_idempotent():
    session, workspace_id = session_with_workspace()
    timestamp = datetime.now(UTC)
    document = Document(
        id=str(uuid4()),
        workspace_id=workspace_id,
        title="Delete me",
        content_hash=None,
        active_version_id=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(document)
    run = create_run(session, workspace_id, "document_delete", {"document_id": document.id})
    execute_run(session, run.id)
    assert document.deleted_at is not None
    execute_run(session, run.id)
    assert run.state == "completed"


def test_workflow_error_details_redact_secret_values():
    details = redact_exception(RuntimeError("Authorization=Bearer-secret api_key: sk-secret"))
    assert "Bearer-secret" not in details["summary"]
    assert "sk-secret" not in details["summary"]
    assert "[redacted]" in details["summary"]


def test_query_runs_are_persisted_separately_from_background_workflows():
    session, workspace_id = session_with_workspace()
    run = create_query_run(session, workspace_id, "Ankara hakkında ne biliyoruz?")
    assert run.state == "queued"
    assert session.query(QueryStepRun).filter_by(query_run_id=run.id).count() == 3


def test_periodic_reconciliation_is_durable_and_idempotent():
    session, workspace_id = session_with_workspace()
    assert schedule_orphan_reconciliation(session) == 1
    run = (
        session.query(WorkflowRun).filter_by(workspace_id=workspace_id, job_type="reconcile").one()
    )
    execute_run(session, run.id)
    assert run.state == "completed"
    assert any(
        event.event_type == "reconciliation_scanned" for event in session.query(WorkflowEvent)
    )


def test_failed_deletion_queues_a_durable_repair_workflow():
    session, workspace_id = session_with_workspace()
    deletion = create_run(session, workspace_id, "document_delete", {})
    execute_run(session, deletion.id)
    repair = (
        session.query(WorkflowRun).filter_by(workspace_id=workspace_id, job_type="reconcile").one()
    )
    assert deletion.state == "failed"
    assert repair.state == "queued"
