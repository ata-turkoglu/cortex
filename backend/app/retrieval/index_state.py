"""Dense-index state transitions and durable reindex requests."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import WorkflowDefinition, WorkflowRun, WorkspaceIndexState
from ..providers.embeddings import EmbeddingConfiguration


class DenseIndexUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class DenseReindexPlan:
    action: str
    reason: str


DENSE_REINDEX_DEFINITION_ID = "dense-reindex"
DENSE_REINDEX_DEFINITION_VERSION = "1"


def plan_dense_reindex(
    session: Session, workspace_id: str, configuration: EmbeddingConfiguration
) -> DenseReindexPlan:
    """Mark an incompatible workspace index before any new vectors can be written."""
    state = session.get(WorkspaceIndexState, workspace_id)
    if state is None:
        raise LookupError(f"missing index state for workspace {workspace_id}")
    if state.embedding_config_hash is None:
        state.dense_state = "reindex_required"
        state.updated_at = datetime.now(UTC)
        return DenseReindexPlan("full_reindex_required", "initial_dense_index_required")
    if state.embedding_config_hash != configuration.fingerprint:
        state.dense_state = "reindex_required"
        state.updated_at = datetime.now(UTC)
        return DenseReindexPlan("full_reindex_required", "embedding_configuration_changed")
    if state.dense_state != "ready":
        return DenseReindexPlan("full_reindex_required", f"dense_index_{state.dense_state}")
    return DenseReindexPlan("none", "embedding_configuration_current")


def mark_dense_index_ready(
    session: Session, workspace_id: str, configuration: EmbeddingConfiguration
) -> None:
    """Commit the active configuration only after a full replacement index succeeds."""
    state = session.get(WorkspaceIndexState, workspace_id)
    if state is None:
        raise LookupError(f"missing index state for workspace {workspace_id}")
    state.embedding_config_hash = configuration.fingerprint
    state.dense_state = "ready"
    state.indexed_at = datetime.now(UTC)
    state.updated_at = datetime.now(UTC)


def create_dense_reindex_run(
    session: Session, workspace_id: str, configuration: EmbeddingConfiguration
) -> WorkflowRun:
    """Create one durable full-reindex request for an incompatible active index."""
    existing = session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.workspace_id == workspace_id,
            WorkflowRun.job_type == "dense_reindex",
            WorkflowRun.state.in_(("queued", "running")),
        )
    )
    if existing:
        return existing
    definition = session.get(WorkflowDefinition, DENSE_REINDEX_DEFINITION_ID)
    if definition is None:
        definition = WorkflowDefinition(
            id=DENSE_REINDEX_DEFINITION_ID,
            version=DENSE_REINDEX_DEFINITION_VERSION,
            name="Dense embedding reindex",
            definition_json='{"steps":["clear_active_vectors","embed","upsert","activate"]}',
        )
        session.add(definition)
    now = datetime.now(UTC)
    run = WorkflowRun(
        id=str(uuid4()),
        workspace_id=workspace_id,
        definition_id=DENSE_REINDEX_DEFINITION_ID,
        state="queued",
        job_type="dense_reindex",
        recovery_state=None,
        payload_json=json.dumps({"embedding_config_hash": configuration.fingerprint}),
        created_at=now,
        updated_at=now,
        finished_at=None,
    )
    session.add(run)
    return run


def require_dense_index_ready(
    state: WorkspaceIndexState, configuration: EmbeddingConfiguration
) -> None:
    if state.dense_state != "ready" or state.embedding_config_hash != configuration.fingerprint:
        raise DenseIndexUnavailable(
            "dense index requires a full reindex for this embedding configuration"
        )
