"""SQLite-backed, versioned workflow state machine used by API and Dramatiq actors."""

import json
import re
import traceback
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import (
    Chunk,
    Document,
    DocumentVersion,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStepRun,
    Workspace,
    WorkspaceLock,
)

DEFINITIONS = {
    "ingestion": (
        "document-ingestion",
        "2",
        "Document ingestion",
        ("parse", "normalize", "chunk", "index"),
    ),
    "dense_reindex": (
        "dense-reindex",
        "2",
        "Dense embedding reindex",
        ("clear_active_vectors", "embed", "upsert", "activate"),
    ),
    "graphrag_reindex": (
        "graphrag-reindex",
        "1",
        "GraphRAG reindex",
        ("snapshot", "materialize", "index", "mirror"),
    ),
    "document_delete": (
        "document-delete",
        "1",
        "Document deletion",
        ("mark", "cleanup", "reconcile"),
    ),
    "workspace_delete": (
        "workspace-delete",
        "1",
        "Workspace deletion",
        ("mark", "cleanup", "reconcile"),
    ),
    "reconcile": ("orphan-reconciliation", "1", "Orphan reconciliation", ("scan", "repair")),
}
LOCK_TYPES = {
    "dense_reindex": "index",
    "graphrag_reindex": "graph",
    "document_delete": "delete",
    "workspace_delete": "delete",
}


def now() -> datetime:
    return datetime.now(UTC)


def concurrency_limit(job_type: str) -> int:
    settings = get_settings()
    if job_type == "ingestion":
        return settings.workflow_ingestion_concurrency
    if job_type == "dense_reindex":
        return settings.workflow_dense_reindex_concurrency
    if job_type == "graphrag_reindex":
        return settings.workflow_graphrag_reindex_concurrency
    return settings.workflow_deletion_concurrency


def ensure_definition(session: Session, job_type: str) -> tuple[str, tuple[str, ...]]:
    definition_id, version, name, steps = DEFINITIONS[job_type]
    definition = session.get(WorkflowDefinition, definition_id)
    body = json.dumps({"version": version, "steps": steps})
    if definition is None:
        session.add(
            WorkflowDefinition(id=definition_id, version=version, name=name, definition_json=body)
        )
    elif definition.version != version:
        definition.version, definition.name, definition.definition_json = version, name, body
    return definition_id, steps


def event(session: Session, run: WorkflowRun, event_type: str, **payload: object) -> None:
    session.add(
        WorkflowEvent(
            id=str(uuid4()),
            workspace_id=run.workspace_id,
            workflow_run_id=run.id,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
            created_at=now(),
        )
    )


def create_run(
    session: Session, workspace_id: str, job_type: str, payload: dict[str, object] | None = None
) -> WorkflowRun:
    if job_type not in DEFINITIONS:
        raise ValueError("unsupported workflow type")
    definition_id, steps = ensure_definition(session, job_type)
    active = session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.workspace_id == workspace_id,
            WorkflowRun.job_type == job_type,
            WorkflowRun.state.in_(("queued", "running", "cancelling")),
        )
    )
    if active:
        return active
    timestamp = now()
    run = WorkflowRun(
        id=str(uuid4()),
        workspace_id=workspace_id,
        definition_id=definition_id,
        state="queued",
        recovery_state=None,
        job_type=job_type,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        created_at=timestamp,
        updated_at=timestamp,
        finished_at=None,
    )
    session.add(run)
    session.flush()
    session.add_all(
        WorkflowStepRun(
            id=str(uuid4()),
            workspace_id=workspace_id,
            workflow_run_id=run.id,
            step_name=step,
            state="pending",
            retry_count=0,
            checkpoint_json=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for step in steps
    )
    event(session, run, "queued", job_type=job_type)
    return run


def request_cancel(session: Session, run: WorkflowRun) -> WorkflowRun:
    if run.state in ("completed", "failed", "cancelled", "interrupted"):
        return run
    run.state, run.updated_at = "cancelling", now()
    event(session, run, "cancellation_requested")
    return run


def retry_from_failed_step(session: Session, run: WorkflowRun) -> WorkflowRun:
    failed = session.scalar(
        select(WorkflowStepRun)
        .where(WorkflowStepRun.workflow_run_id == run.id, WorkflowStepRun.state == "failed")
        .order_by(WorkflowStepRun.created_at)
    )
    if not failed and run.state == "interrupted":
        failed = session.scalar(
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.workflow_run_id == run.id,
                WorkflowStepRun.state != "completed",
            )
            .order_by(WorkflowStepRun.created_at)
        )
    if not failed:
        raise ValueError("workflow has no failed or interrupted step")
    failed.state, failed.retry_count, failed.updated_at = "pending", failed.retry_count + 1, now()
    for step in session.scalars(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run.id,
            WorkflowStepRun.created_at > failed.created_at,
        )
    ):
        step.state, step.checkpoint_json, step.updated_at = "pending", None, now()
    run.state, run.recovery_state, run.finished_at, run.updated_at = (
        "queued",
        "retrying",
        None,
        now(),
    )
    event(session, run, "retry_requested", step=failed.step_name)
    return run


def redact_exception(exc: Exception) -> dict[str, str]:
    # Do not include source input; redact common credential-like assignments from traceback text.
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    detail = re.sub(
        r"(?i)\b(api[_-]?key|token|password|authorization)\b\s*([=:])\s*[^\s,;]+",
        r"\1\2[redacted]",
        detail,
    )
    return {"summary": detail[:500] or "workflow failed"}


def apply_deletion_cleanup(session: Session, run: WorkflowRun) -> None:
    """Idempotently tombstone relational document records at the cleanup checkpoint."""
    payload = json.loads(run.payload_json or "{}")
    timestamp = now()
    documents = select(Document).where(Document.workspace_id == run.workspace_id)
    if run.job_type == "document_delete":
        document_id = payload.get("document_id")
        if not isinstance(document_id, str):
            raise ValueError("document deletion requires document_id")
        documents = documents.where(Document.id == document_id)
    for document in session.scalars(documents).all():
        document.deleted_at = document.deleted_at or timestamp
        document.updated_at = timestamp
        for version in session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        ):
            version.deleted_at = version.deleted_at or timestamp
        for chunk in session.scalars(select(Chunk).where(Chunk.document_id == document.id)):
            chunk.deleted_at = chunk.deleted_at or timestamp
    if run.job_type == "workspace_delete":
        workspace = session.get(Workspace, run.workspace_id)
        if workspace:
            workspace.state = "deleted"
            workspace.deleted_at = workspace.deleted_at or timestamp
            workspace.updated_at = timestamp


def execute_run(session: Session, run_id: str) -> None:
    run = session.get(WorkflowRun, run_id)
    if run is None or run.state not in ("queued", "running", "cancelling"):
        return
    if run.state == "cancelling":
        run.state = "cancelled"
        run.finished_at = now()
        run.updated_at = now()
        event(session, run, "cancelled", step=None)
        return
    running_count = session.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.job_type == run.job_type,
            WorkflowRun.state == "running",
            WorkflowRun.id != run.id,
        )
        .with_only_columns(func.count())
    )
    if running_count >= concurrency_limit(run.job_type):
        event(session, run, "blocked", reason="stage_concurrency_limit")
        return
    lock_type = LOCK_TYPES.get(run.job_type)
    if lock_type and run.state == "queued":
        held = session.scalar(
            select(WorkspaceLock).where(
                WorkspaceLock.workspace_id == run.workspace_id, WorkspaceLock.lock_type == lock_type
            )
        )
        if held and held.workflow_run_id != run.id:
            event(session, run, "blocked", lock_type=lock_type)
            return
        if not held:
            session.add(
                WorkspaceLock(
                    id=str(uuid4()),
                    workspace_id=run.workspace_id,
                    lock_type=lock_type,
                    workflow_run_id=run.id,
                    acquired_at=now(),
                )
            )
    run.state, run.updated_at = "running", now()
    event(session, run, "started")
    try:
        steps = session.scalars(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.workflow_run_id == run.id)
            .order_by(WorkflowStepRun.created_at)
        ).all()
        for step in steps:
            if step.state == "completed":
                continue
            if run.state == "cancelling":
                run.state, run.finished_at, run.updated_at = "cancelled", now(), now()
                event(session, run, "cancelled", step=step.step_name)
                break
            step.state, step.updated_at = "running", now()
            event(session, run, "step_started", step=step.step_name)
            if step.step_name == "cleanup" and run.job_type in {
                "document_delete",
                "workspace_delete",
            }:
                apply_deletion_cleanup(session, run)
            # External parsing/model work is deliberately invoked by specialized worker adapters;
            # this durable boundary only commits short, idempotent checkpoints.
            step.state, step.checkpoint_json, step.updated_at = (
                "completed",
                json.dumps({"completed": True}),
                now(),
            )
            event(session, run, "step_completed", step=step.step_name)
        else:
            run.state, run.finished_at, run.updated_at = "completed", now(), now()
            event(session, run, "completed")
    except Exception as exc:
        run.state, run.finished_at, run.updated_at = "failed", now(), now()
        event(session, run, "failed", details=redact_exception(exc))
    finally:
        if run.state in ("completed", "failed", "cancelled") and lock_type:
            lock = session.scalar(
                select(WorkspaceLock).where(
                    WorkspaceLock.workflow_run_id == run.id, WorkspaceLock.lock_type == lock_type
                )
            )
            if lock:
                session.delete(lock)


def recover_stale(session: Session) -> int:
    stale = session.scalars(
        select(WorkflowRun).where(WorkflowRun.state.in_(("running", "cancelling")))
    ).all()
    for run in stale:
        run.state, run.recovery_state, run.updated_at = "interrupted", "restart_detected", now()
        event(session, run, "interrupted", reason="worker_restart")
    return len(stale)


def cleanup_retention(session: Session) -> int:
    """Soft-delete completed historical workflow state after the configured retention period."""
    cutoff = now() - timedelta(days=get_settings().workflow_retention_days)
    completed = session.scalars(
        select(WorkflowRun).where(
            WorkflowRun.finished_at.is_not(None),
            WorkflowRun.finished_at < cutoff,
            WorkflowRun.deleted_at.is_(None),
        )
    ).all()
    for run in completed:
        run.deleted_at = now()
    return len(completed)
