"""Small durable state records for retrying a knowledge_reindex run."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import KnowledgeReindexRunContext


def _now() -> datetime:
    return datetime.now(UTC)


def create_context(
    session: Session,
    *,
    workspace_id: str,
    workflow_run_id: str,
    generation_id: str,
    source_fingerprint: str,
) -> KnowledgeReindexRunContext:
    existing = (
        session.query(KnowledgeReindexRunContext)
        .filter_by(workflow_run_id=workflow_run_id)
        .one_or_none()
    )
    if existing:
        if (
            existing.generation_id != generation_id
            or existing.source_fingerprint != source_fingerprint
        ):
            raise ValueError("workflow run context cannot change candidate generation")
        return existing
    timestamp = _now()
    context = KnowledgeReindexRunContext(
        id=str(uuid4()), workspace_id=workspace_id, workflow_run_id=workflow_run_id,
        generation_id=generation_id, source_fingerprint=source_fingerprint,
        state_json="{}", created_at=timestamp, updated_at=timestamp,
    )
    session.add(context)
    return context


def checkpoint(context: KnowledgeReindexRunContext, stage: str, values: dict[str, object]) -> None:
    """Store identifiers/fingerprints/metrics only; reject accidental source-text persistence."""
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True)
    if "source_text" in encoded.lower() or "content" in encoded.lower():
        raise ValueError("knowledge run context may not store source text")
    state = json.loads(context.state_json)
    state[stage] = values
    context.state_json = json.dumps(state, ensure_ascii=False, sort_keys=True)
    context.updated_at = _now()
