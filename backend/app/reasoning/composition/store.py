"""Workspace-isolated persistence for durable composition checkpoints."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ...models import CompositionRunRecord, ResearchRunRecord
from .schemas import CompositionCheckpoint


def _now() -> datetime:
    return datetime.now(UTC)


def create_composition_run(
    session: Session,
    workspace_id: str,
    research_run_id: str,
    title: str,
    evidence_ids: tuple[str, ...],
) -> CompositionCheckpoint:
    research = session.get(ResearchRunRecord, research_run_id)
    if research is None or research.workspace_id != workspace_id:
        raise LookupError("research run not found in workspace")
    run_id = str(uuid4())
    checkpoint = CompositionCheckpoint(
        run_id=run_id, research_run_id=research_run_id, workspace_id=workspace_id,
        title=title, evidence_ids=evidence_ids,
    )
    timestamp = _now()
    session.add(
        CompositionRunRecord(
            id=run_id, workspace_id=workspace_id, research_run_id=research_run_id,
            schema_version=checkpoint.schema_version, revision=1, state=checkpoint.state,
            title=title, checkpoint_json=checkpoint.model_dump_json(), failure_json=None,
            created_at=timestamp, updated_at=timestamp, finished_at=None,
        )
    )
    session.flush()
    return checkpoint


def load_composition_run(
    session: Session, workspace_id: str, run_id: str
) -> tuple[CompositionCheckpoint, int]:
    record = session.get(CompositionRunRecord, run_id)
    if record is None or record.workspace_id != workspace_id:
        raise LookupError("composition run not found in workspace")
    return CompositionCheckpoint.model_validate_json(record.checkpoint_json), record.revision


def save_composition_run(
    session: Session, checkpoint: CompositionCheckpoint, *, expected_revision: int
) -> int:
    checkpoint = CompositionCheckpoint.model_validate(checkpoint.model_dump())
    record = session.get(CompositionRunRecord, checkpoint.run_id)
    if record is None or record.workspace_id != checkpoint.workspace_id:
        raise LookupError("composition run not found in workspace")
    if record.revision != expected_revision:
        raise RuntimeError("composition run revision conflict")
    record.revision += 1
    record.state = checkpoint.state
    record.checkpoint_json = checkpoint.model_dump_json()
    record.failure_json = (
        json.dumps({"issues": checkpoint.validation_issues}, ensure_ascii=False)
        if checkpoint.state == "failed"
        else None
    )
    record.updated_at = _now()
    if checkpoint.state in {"ready", "failed"}:
        record.finished_at = record.updated_at
    return record.revision
