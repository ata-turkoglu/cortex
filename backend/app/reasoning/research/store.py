"""Workspace-isolated persistence for durable research checkpoints."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ...models import ResearchRunRecord, Workspace
from .schemas import ResearchCheckpoint


def _now() -> datetime:
    return datetime.now(UTC)


def create_research_run(
    session: Session,
    workspace_id: str,
    goal: str,
    *,
    conversation_id: str | None = None,
    generation_id: str | None = None,
) -> ResearchCheckpoint:
    if session.get(Workspace, workspace_id) is None:
        raise LookupError("workspace not found")
    run_id = str(uuid4())
    checkpoint = ResearchCheckpoint(
        run_id=run_id, workspace_id=workspace_id, goal=goal, generation_id=generation_id
    )
    timestamp = _now()
    session.add(
        ResearchRunRecord(
            id=run_id, workspace_id=workspace_id, conversation_id=conversation_id,
            schema_version=checkpoint.schema_version, revision=1, state=checkpoint.state,
            goal=goal, generation_id=generation_id,
            checkpoint_json=checkpoint.model_dump_json(), failure_json=None,
            created_at=timestamp, updated_at=timestamp, finished_at=None,
        )
    )
    session.flush()
    return checkpoint


def load_research_run(
    session: Session, workspace_id: str, run_id: str
) -> tuple[ResearchCheckpoint, int]:
    record = session.get(ResearchRunRecord, run_id)
    if record is None or record.workspace_id != workspace_id:
        raise LookupError("research run not found in workspace")
    return ResearchCheckpoint.model_validate_json(record.checkpoint_json), record.revision


def save_research_run(
    session: Session,
    checkpoint: ResearchCheckpoint,
    *,
    expected_revision: int,
) -> int:
    checkpoint = ResearchCheckpoint.model_validate(checkpoint.model_dump())
    record = session.get(ResearchRunRecord, checkpoint.run_id)
    if record is None or record.workspace_id != checkpoint.workspace_id:
        raise LookupError("research run not found in workspace")
    if record.revision != expected_revision:
        raise RuntimeError("research run revision conflict")
    record.revision += 1
    record.state = checkpoint.state
    record.checkpoint_json = checkpoint.model_dump_json()
    record.failure_json = (
        json.dumps({"issues": checkpoint.issues}, ensure_ascii=False)
        if checkpoint.state == "failed"
        else None
    )
    record.updated_at = _now()
    if checkpoint.state in {"ready", "partial", "unsupported", "failed"}:
        record.finished_at = record.updated_at
    return record.revision
