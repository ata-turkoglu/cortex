"""REST and SSE surface for persistent workflow monitoring and commands."""
# ruff: noqa: B008  # FastAPI dependency injection intentionally uses parameter defaults.

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import WorkflowEvent, WorkflowRun, WorkflowStepRun
from ..workflows.service import create_run, request_cancel, retry_from_failed_step
from .workspaces import get_session

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    workspace_id: str
    job_type: str = Field(
        pattern="^(ingestion|dense_reindex|graphrag_reindex|document_delete|workspace_delete|reconcile)$"
    )
    payload: dict[str, object] = Field(default_factory=dict)


class WorkflowCommand(BaseModel):
    pass


class StepRead(BaseModel):
    id: str
    step_name: str
    state: str
    retry_count: int
    checkpoint_json: str | None
    model_config = {"from_attributes": True}


class WorkflowRead(BaseModel):
    id: str
    workspace_id: str
    definition_id: str
    job_type: str
    state: str
    recovery_state: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    steps: list[StepRead] = []


class WorkflowEventRead(BaseModel):
    id: str
    event_type: str
    payload_json: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


def serialize(session: Session, run: WorkflowRun) -> WorkflowRead:
    return WorkflowRead.model_validate(
        {
            **{
                key: getattr(run, key)
                for key in (
                    "id",
                    "workspace_id",
                    "definition_id",
                    "job_type",
                    "state",
                    "recovery_state",
                    "created_at",
                    "updated_at",
                    "finished_at",
                )
            },
            "steps": session.scalars(
                select(WorkflowStepRun)
                .where(WorkflowStepRun.workflow_run_id == run.id)
                .order_by(WorkflowStepRun.created_at)
            ).all(),
        }
    )


def dispatch(run_id: str) -> None:
    from ..workers.broker import execute_workflow

    try:
        execute_workflow.send(run_id)
    except Exception:
        # State remains queued and can be retried when Redis recovers.
        pass


@router.get("", response_model=list[WorkflowRead])
def list_runs(
    workspace_id: str | None = None,
    session: Session = Depends(get_session),  # noqa: B008
):
    query = (
        select(WorkflowRun)
        .where(WorkflowRun.deleted_at.is_(None))
        .order_by(WorkflowRun.updated_at.desc())
    )
    if workspace_id:
        query = query.where(WorkflowRun.workspace_id == workspace_id)
    return [serialize(session, run) for run in session.scalars(query).all()]


@router.post("", response_model=WorkflowRead, status_code=201)
def create(payload: WorkflowCreate, session: Session = Depends(get_session)):  # noqa: B008
    try:
        run = create_run(session, payload.workspace_id, payload.job_type, payload.payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.flush()
    dispatch(run.id)
    return serialize(session, run)


@router.get("/{run_id}", response_model=WorkflowRead)
def inspect(run_id: str, session: Session = Depends(get_session)):  # noqa: B008
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "workflow not found")
    return serialize(session, run)


@router.post("/{run_id}/cancel", response_model=WorkflowRead)
def cancel(  # noqa: B008
    run_id: str, _: WorkflowCommand, session: Session = Depends(get_session)
):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "workflow not found")
    return serialize(session, request_cancel(session, run))


@router.post("/{run_id}/retry", response_model=WorkflowRead)
def retry(  # noqa: B008
    run_id: str, _: WorkflowCommand, session: Session = Depends(get_session)
):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "workflow not found")
    try:
        retry_from_failed_step(session, run)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.flush()
    dispatch(run.id)
    return serialize(session, run)


@router.get("/{run_id}/events")
async def stream(
    run_id: str,
    after: str | None = None,
    last_event_id: str | None = Header(default=None),
):
    """SSE reconnect uses the last received event id and then sends current state."""

    async def events():
        cursor = after or last_event_id or ""
        while True:
            from ..core.database import SessionLocal

            session = SessionLocal()
            try:
                rows = session.scalars(
                    select(WorkflowEvent)
                    .where(WorkflowEvent.workflow_run_id == run_id)
                    .order_by(WorkflowEvent.created_at)
                ).all()
                if cursor:
                    seen_cursor = False
                    rows = [
                        row
                        for row in rows
                        if (seen_cursor := seen_cursor or row.id == cursor) and row.id != cursor
                    ]
                for row in rows:
                    cursor = row.id
                    yield (
                        f"id: {row.id}\nevent: {row.event_type}\n"
                        f"data: {row.payload_json or '{}'}\n\n"
                    )
                run = session.get(WorkflowRun, run_id)
                if run and run.state in ("completed", "failed", "cancelled", "interrupted"):
                    body = json.dumps(
                        {"state": run.state, "updated_at": run.updated_at.isoformat()}
                    )
                    yield f"event: state\ndata: {body}\n\n"
                    return
            finally:
                session.close()
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/events/history", response_model=list[WorkflowEventRead])
def event_history(run_id: str, session: Session = Depends(get_session)):  # noqa: B008
    if not session.get(WorkflowRun, run_id):
        raise HTTPException(404, "workflow not found")
    return session.scalars(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_run_id == run_id)
        .order_by(WorkflowEvent.created_at)
    ).all()
