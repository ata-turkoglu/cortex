"""Durable ingestion workflow record creation; execution is delegated to workers."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import WorkflowDefinition, WorkflowRun

INGESTION_DEFINITION_ID = "document-ingestion"
INGESTION_DEFINITION_VERSION = "1"


def create_ingestion_run(session: Session, workspace_id: str, document_version_id: str, *, queued: bool = False) -> WorkflowRun:
    definition = session.get(WorkflowDefinition, INGESTION_DEFINITION_ID)
    if definition is None:
        definition = WorkflowDefinition(
            id=INGESTION_DEFINITION_ID,
            version=INGESTION_DEFINITION_VERSION,
            name="Document ingestion",
            definition_json='{"steps":["parse","normalize","chunk","index"]}',
        )
        session.add(definition)
    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        id=str(uuid4()), workspace_id=workspace_id, definition_id=INGESTION_DEFINITION_ID,
        state="queued" if queued else "completed", job_type="ingestion", recovery_state=None,
        payload_json=json.dumps({"document_version_id": document_version_id}),
        created_at=now, updated_at=now, finished_at=None if queued else now,
    )
    session.add(run)
    return run
