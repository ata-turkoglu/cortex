import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy import select

from ..core.config import get_settings
from ..core.database import run_with_lock_retry
from ..models import WorkflowRun
from ..workflows.service import (
    cleanup_retention,
    execute_run,
    recover_stale,
    schedule_orphan_reconciliation,
)

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
    except Exception:
        return False
    return True


@dramatiq.actor(max_retries=3)
def recover_stale_jobs() -> None:
    run_with_lock_retry(recover_stale)


@dramatiq.actor(max_retries=3)
def execute_workflow(run_id: str) -> None:
    """Execute short durable steps; Dramatiq retry is safe because checkpoints persist."""
    from ..core.database import SessionLocal

    session = SessionLocal()
    try:
        run = session.get(WorkflowRun, run_id)
        is_graph_reindex = bool(run and run.job_type == "graphrag_reindex")
    finally:
        session.close()
    if is_graph_reindex:
        from ..workflows.graphrag import execute as execute_graphrag

        execute_graphrag(run_id, run_with_lock_retry)
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
