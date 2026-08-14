import json
import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy import select

from ..core.config import get_settings
from ..core.database import run_with_lock_retry
from ..core.logging import configure_logging
from ..models import Document, DocumentVersion, WorkflowRun
from ..workflows.service import (
    cleanup_retention,
    execute_run,
    recover_stale,
    schedule_orphan_reconciliation,
)
from ..workflows.service import (
    event as workflow_event,
)

configure_logging()
logger = logging.getLogger("cortex.worker")
broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)


def dispatch_workflow(run_id: str) -> bool:
    """Best-effort dispatch after a workflow run is durably committed.

    A broker outage must not turn a successfully queued command into an API
    failure. The persisted run remains visible and can be dispatched by the
    worker/retry path when Redis is available again.
    """
    try:
        execute_workflow.send(run_id)
        logger.info("workflow dispatched: run_id=%s", run_id)
    except Exception:
        logger.exception("workflow dispatch failed: run_id=%s", run_id)
        return False
    return True


@dramatiq.actor(max_retries=3)
def recover_stale_jobs() -> None:
    queued_ids: list[str] = []

    def recover_and_collect(session):
        recovered = recover_stale(session)
        queued_ids.extend(
            session.scalars(
                select(WorkflowRun.id).where(
                    WorkflowRun.state == "queued",
                    WorkflowRun.deleted_at.is_(None),
                )
            ).all()
        )
        return recovered

    recovered = run_with_lock_retry(recover_and_collect)
    logger.info(
        "workflow recovery: interrupted=%s queued_for_dispatch=%s",
        recovered,
        len(queued_ids),
    )
    for run_id in queued_ids:
        execute_workflow.send(run_id)


@dramatiq.actor(max_retries=3)
def execute_workflow(run_id: str) -> None:
    """Execute short durable steps; Dramatiq retry is safe because checkpoints persist."""
    from ..core.database import SessionLocal
    from ..core.settings_service import load_runtime_settings

    session = SessionLocal()
    try:
        # The API and worker are separate processes. Apply the persisted global
        # settings in this process before resolving any workflow provider/model.
        load_runtime_settings(session)
        run = session.get(WorkflowRun, run_id)
        is_graph_reindex = bool(run and run.job_type == "graphrag_reindex")
        if run:
            logger.info(
                "workflow received: run_id=%s type=%s state=%s workspace_id=%s",
                run.id,
                run.job_type,
                run.state,
                run.workspace_id,
            )
        else:
            logger.warning("workflow not found: run_id=%s", run_id)
    finally:
        session.close()
    if is_graph_reindex:
        from ..workflows.graphrag import execute as execute_graphrag

        execute_graphrag(run_id, run_with_lock_retry)
        return
    if run and run.job_type in {"ingestion", "dense_reindex"}:
        from ..retrieval.indexing import rebuild_active_workspace

        def claim_index(session):
            active = session.get(WorkflowRun, run_id)
            if not active or active.state != "queued":
                logger.info(
                    "workflow skipped: run_id=%s state=%s",
                    run_id,
                    active.state if active else "missing",
                )
                return None
            from datetime import UTC, datetime

            payload = json.loads(active.payload_json or "{}")
            version_id = payload.get("document_version_id")
            filename = None
            if isinstance(version_id, str):
                version = session.get(DocumentVersion, version_id)
                document = session.get(Document, version.document_id) if version else None
                filename = document.title if document else None
            active.state, active.updated_at = "running", datetime.now(UTC)
            workflow_event(session, active, "started")
            logger.info(
                "workflow running: run_id=%s workspace_id=%s file=%s",
                active.id,
                active.workspace_id,
                filename or "unknown",
            )
            return active.workspace_id

        workspace_id = run_with_lock_retry(claim_index)
        if not workspace_id:
            return
        index_session = SessionLocal()
        try:
            logger.info("index rebuild started: run_id=%s workspace_id=%s", run_id, workspace_id)
            summary = rebuild_active_workspace(index_session, workspace_id)
            index_session.commit()
            logger.info(
                "index rebuild completed: run_id=%s workspace_id=%s chunks=%s",
                run_id,
                summary.workspace_id,
                summary.chunk_count,
            )
        except Exception as exc:
            index_session.rollback()
            failure_summary = str(exc)[:500]
            logger.exception("index rebuild failed: run_id=%s error=%s", run_id, failure_summary)

            def mark_failed(session):
                from datetime import UTC, datetime

                active = session.get(WorkflowRun, run_id)
                if active and active.state == "running":
                    active.state, active.finished_at, active.updated_at = (
                        "failed",
                        datetime.now(UTC),
                        datetime.now(UTC),
                    )
                    workflow_event(session, active, "failed", details={"summary": failure_summary})

            run_with_lock_retry(mark_failed)
            raise
        finally:
            index_session.close()

        def complete_index(session):
            active = session.get(WorkflowRun, run_id)
            if active and active.state == "running":
                execute_run(session, run_id)

        run_with_lock_retry(complete_index)
        logger.info("workflow completed: run_id=%s", run_id)
        return
    run_with_lock_retry(lambda session: execute_run(session, run_id))
    from ..workflows.reconciliation import cleanup_external, snapshot_external_cleanup
    from ..workflows.service import create_run, event

    session = SessionLocal()
    try:
        snapshot = snapshot_external_cleanup(session, run_id)
        session.commit()
    finally:
        session.close()
    if not snapshot:
        return
    try:
        cleanup_external(snapshot)
    except Exception:

        def queue_repair(session):
            repair = create_run(
                session,
                snapshot.workspace_id,
                "reconcile",
                {"requested_by": run_id, "scope": "external"},
            )
            event(session, repair, "repair_queued", failed_workflow_id=run_id)

        run_with_lock_retry(queue_repair)
        raise


@dramatiq.actor(max_retries=1)
def cleanup_workflow_retention() -> None:
    run_with_lock_retry(cleanup_retention)


@dramatiq.actor(max_retries=1)
def reconcile_orphans() -> None:
    queued_ids: list[str] = []

    def schedule_and_collect(session):
        count = schedule_orphan_reconciliation(session)
        queued_ids.extend(
            session.scalars(
                select(WorkflowRun.id).where(
                    WorkflowRun.job_type == "reconcile",
                    WorkflowRun.state == "queued",
                    WorkflowRun.deleted_at.is_(None),
                )
            ).all()
        )
        return count

    # Dispatch only after run_with_lock_retry commits the durable records.
    run_with_lock_retry(schedule_and_collect)
    for run_id in queued_ids:
        execute_workflow.send(run_id)


@dramatiq.actor(max_retries=1)
def execute_query_synthesis(query_run_id: str) -> None:
    from ..chat.execution import synthesize_with_openai
    from ..core.database import SessionLocal

    synthesize_with_openai(query_run_id, SessionLocal)


@dramatiq.actor(max_retries=0)
def execute_graphrag_query(query_run_id: str) -> None:
    """The worker-only GraphRAG query entrypoint."""
    from ..core.database import SessionLocal
    from ..workflows.graphrag_query import execute

    session = SessionLocal()
    try:
        execute(session, query_run_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dramatiq.actor(max_retries=1)
def summarize_conversation(conversation_id: str) -> None:
    from ..chat.execution import summarize_conversation_with_openai
    from ..core.database import SessionLocal

    summarize_conversation_with_openai(conversation_id, SessionLocal)
