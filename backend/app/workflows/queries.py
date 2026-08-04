"""Durable query-run records, intentionally separate from background workflow runs."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import QueryRun, QueryStepRun

QUERY_STEPS = ("route", "retrieve", "synthesize")


def create_query_run(
    session: Session, workspace_id: str, query_text: str, conversation_id: str | None = None
) -> QueryRun:
    if not query_text.strip():
        raise ValueError("query text is required")
    timestamp = datetime.now(UTC)
    run = QueryRun(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_text=query_text,
        state="queued",
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(run)
    session.flush()
    session.add_all(
        QueryStepRun(
            id=str(uuid4()),
            workspace_id=workspace_id,
            query_run_id=run.id,
            step_name=step,
            state="pending",
            created_at=timestamp,
            updated_at=timestamp,
        )
        for step in QUERY_STEPS
    )
    return run
