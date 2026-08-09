"""Cross-store cleanup is deliberately split from short SQLite transactions."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.qdrant import get_qdrant_client
from ..models import DocumentVersion, WorkflowRun
from ..retrieval.qdrant import WorkspaceQdrantStore


@dataclass(frozen=True)
class ExternalCleanupSnapshot:
    workspace_id: str
    document_id: str | None
    source_paths: tuple[Path, ...]
    normalized_paths: tuple[Path, ...]


def snapshot_external_cleanup(session: Session, run_id: str) -> ExternalCleanupSnapshot | None:
    run = session.get(WorkflowRun, run_id)
    if (
        not run
        or run.state != "completed"
        or run.job_type not in {"document_delete", "workspace_delete"}
    ):
        return None
    versions = session.scalars(
        select(DocumentVersion).where(DocumentVersion.workspace_id == run.workspace_id)
    ).all()
    payload = __import__("json").loads(run.payload_json or "{}")
    document_id = payload.get("document_id")
    if document_id:
        versions = [version for version in versions if version.document_id == document_id]
    return ExternalCleanupSnapshot(
        workspace_id=run.workspace_id,
        document_id=document_id,
        source_paths=tuple(Path(value.source_path) for value in versions if value.source_path),
        normalized_paths=tuple(
            Path(value.normalized_path) for value in versions if value.normalized_path
        ),
    )


def cleanup_external(snapshot: ExternalCleanupSnapshot) -> None:
    """Run filesystem/Qdrant work only after snapshot_external_cleanup closes the session."""
    store = WorkspaceQdrantStore(get_qdrant_client(), snapshot.workspace_id)
    if snapshot.document_id:
        store.delete_document("chunks", snapshot.document_id)
    for path in (*snapshot.source_paths, *snapshot.normalized_paths):
        if path.exists():
            path.unlink()
