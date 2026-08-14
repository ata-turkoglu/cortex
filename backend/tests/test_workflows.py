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
    WorkflowStepRun,
    Workspace,
    WorkspaceLock,
)
from app.workflows.queries import create_query_run
from app.workflows.service import (
    LOCK_TYPES,
    claim_queued_workflow,
    cleanup_retention,
    clear_workflow_history,
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


def test_queued_workflow_cancels_without_a_worker_claiming_it():
    session, workspace_id = session_with_workspace()
    run = create_run(session, workspace_id, "ingestion")

    request_cancel(session, run)

    assert run.state == "cancelled"
    assert run.finished_at is not None


def test_queued_workflow_can_be_redispatched_after_a_transient_broker_failure():
    session, workspace_id = session_with_workspace()
    run = create_run(session, workspace_id, "ingestion")

    retry_from_failed_step(session, run)

    assert run.state == "queued"
    assert any(
        item.event_type == "redispatch_requested"
        for item in session.query(WorkflowEvent).filter_by(workflow_run_id=run.id)
    )


def test_failed_workflow_without_a_failed_checkpoint_retries_from_first_pending_step():
    session, workspace_id = session_with_workspace()
    run = create_run(session, workspace_id, "ingestion")
    run.state = "failed"

    retry_from_failed_step(session, run)

    assert run.state == "queued"
    assert run.recovery_state == "retrying"
    first_step = (
        session.query(WorkflowStepRun)
        .filter_by(workflow_run_id=run.id)
        .order_by(WorkflowStepRun.created_at)
        .first()
    )
    assert first_step.retry_count == 1


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


def test_ingestion_claim_respects_the_global_concurrency_limit(monkeypatch):
    session, workspace_id = session_with_workspace()
    first = create_run(session, workspace_id, "ingestion")
    second = create_run(session, str(uuid4()), "ingestion")
    third = create_run(session, str(uuid4()), "ingestion")
    monkeypatch.setattr("app.workflows.service.concurrency_limit", lambda _: 2)

    assert claim_queued_workflow(session, first) is True
    assert claim_queued_workflow(session, second) is True
    assert claim_queued_workflow(session, third) is False
    assert third.state == "queued"
    assert any(
        event.event_type == "blocked"
        for event in session.query(WorkflowEvent).filter_by(workflow_run_id=third.id)
    )


def test_ingestion_uses_the_workspace_index_lock():
    assert LOCK_TYPES["ingestion"] == "index"


def test_clear_workflow_history_preserves_active_runs():
    session, workspace_id = session_with_workspace()
    completed = create_run(session, workspace_id, "dense_reindex")
    completed.state = "completed"
    active = create_run(session, workspace_id, "dense_reindex")
    active.state = "running"

    assert clear_workflow_history(session) == 1
    assert completed.deleted_at is not None
    assert active.deleted_at is None


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


def test_interrupted_owner_does_not_leave_a_workspace_delete_lock_stuck():
    session, workspace_id = session_with_workspace()
    owner = create_run(session, workspace_id, "document_delete", {"document_id": "old"})
    owner.state = "interrupted"
    session.add(
        WorkspaceLock(
            id=str(uuid4()),
            workspace_id=workspace_id,
            lock_type="delete",
            workflow_run_id=owner.id,
            acquired_at=datetime.now(UTC),
        )
    )
    next_run = create_run(session, workspace_id, "document_delete", {"document_id": "new"})

    execute_run(session, next_run.id)

    assert next_run.state == "completed"
    assert not session.query(WorkspaceLock).all()


def test_workflow_error_details_redact_secret_values():
    details = redact_exception(RuntimeError("Authorization=Bearer-secret api_key: sk-secret"))
    assert "Bearer-secret" not in details["summary"]
    assert "sk-secret" not in details["summary"]
    assert "[redacted]" in details["summary"]


def test_workflow_error_details_keep_the_actionable_tail():
    details = redact_exception(RuntimeError(("traceback context\\n" * 80) + "ValueError: cause"))

    assert details["summary"].endswith("ValueError: cause")


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


def test_workflow_dispatch_keeps_the_durable_run_queued_when_redis_is_unavailable(monkeypatch):
    from app.workers.broker import dispatch_workflow, execute_workflow

    def unavailable(_run_id: str):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(execute_workflow, "send", unavailable)
    assert dispatch_workflow("durable-run-id") is False


def test_workflow_dispatch_schedules_an_idempotent_delayed_fallback(monkeypatch):
    from app.workers.broker import dispatch_workflow, execute_workflow

    sent: list[tuple[str, object]] = []
    monkeypatch.setattr(execute_workflow, "send", lambda run_id: sent.append(("now", run_id)))
    monkeypatch.setattr(
        execute_workflow,
        "send_with_options",
        lambda **options: sent.append(("later", options)),
    )

    assert dispatch_workflow("durable-run-id") is True
    assert sent == [
        ("now", "durable-run-id"),
        ("later", {"args": ("durable-run-id",), "delay": 5_000}),
    ]
