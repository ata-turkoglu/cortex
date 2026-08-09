"""Durable ingestion workflow record creation; execution is delegated to workers."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import WorkflowDefinition, WorkflowRun, WorkflowStepRun

INGESTION_DEFINITION_ID = "document-ingestion"
INGESTION_DEFINITION_VERSION = "3"


def create_ingestion_run(
    session: Session, workspace_id: str, document_version_id: str, *, queued: bool = False
) -> WorkflowRun:
    definition = session.get(WorkflowDefinition, INGESTION_DEFINITION_ID)
    if definition is None:
        definition = WorkflowDefinition(
            id=INGESTION_DEFINITION_ID,
            version=INGESTION_DEFINITION_VERSION,
            name="Document ingestion with logical boundaries",
            definition_json=(
                '{"steps":["parse","normalize","logical_documents","chunk","index"]}'
            ),
        )
        session.add(definition)
    elif definition.version != INGESTION_DEFINITION_VERSION:
        definition.version = INGESTION_DEFINITION_VERSION
        definition.name = "Document ingestion with logical boundaries"
        definition.definition_json = (
            '{"steps":["parse","normalize","logical_documents","chunk","index"]}'
        )
    now = datetime.now(UTC)
    run = WorkflowRun(
        id=str(uuid4()),
        workspace_id=workspace_id,
        definition_id=INGESTION_DEFINITION_ID,
        state="queued" if queued else "completed",
        job_type="ingestion",
        recovery_state=None,
        payload_json=json.dumps({"document_version_id": document_version_id}),
        created_at=now,
        updated_at=now,
        finished_at=None if queued else now,
    )
    session.add(run)
    session.add_all(
        WorkflowStepRun(
            id=str(uuid4()),
            workspace_id=workspace_id,
            workflow_run_id=run.id,
            step_name=step_name,
            state="pending" if queued else "completed",
            retry_count=0,
            checkpoint_json=None if queued else '{"completed": true}',
            created_at=now,
            updated_at=now,
        )
        for step_name in ("parse", "normalize", "logical_documents", "chunk", "index")
    )
    return run
