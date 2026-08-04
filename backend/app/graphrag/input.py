"""Materialize workspace-normalized documents for a deferred GraphRAG index run."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, DocumentVersion


@dataclass(frozen=True)
class GraphRAGInputManifest:
    workspace_id: str
    input_root: Path
    document_version_ids: tuple[str, ...]


@dataclass(frozen=True)
class GraphRAGInputDocument:
    document_version_id: str
    normalized_path: Path


class GraphRAGInputMaterializer:
    """Copy only active, workspace-owned normalized Markdown into GraphRAG input."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    def materialize(
        self, session: Session, workspace_id: str, graph_root: Path
    ) -> GraphRAGInputManifest:
        return self.write(self.collect(session, workspace_id), workspace_id, graph_root)

    def collect(self, session: Session, workspace_id: str) -> tuple[GraphRAGInputDocument, ...]:
        """Collect DB-backed inputs; callers can close the transaction before file I/O."""
        rows = list(
            session.execute(
                select(DocumentVersion)
                .join(Document)
                .where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                    DocumentVersion.workspace_id == workspace_id,
                    DocumentVersion.deleted_at.is_(None),
                    DocumentVersion.normalized_path.is_not(None),
                )
            ).scalars()
        )
        documents = []
        for version in rows:
            source = self._safe_normalized_path(version.normalized_path)
            if not source.is_file():
                raise FileNotFoundError(f"normalized document is missing: {version.id}")
            documents.append(GraphRAGInputDocument(version.id, source))
        return tuple(documents)

    def write(
        self,
        documents: tuple[GraphRAGInputDocument, ...],
        workspace_id: str,
        graph_root: Path,
    ) -> GraphRAGInputManifest:
        """Materialize a previously collected input snapshot without a database session."""
        input_root = graph_root / "input"
        input_root.mkdir(parents=True, exist_ok=True)
        version_ids: list[str] = []
        for document in documents:
            target = input_root / f"{document.document_version_id}.md"
            content = document.normalized_path.read_text(encoding="utf-8")
            target.write_text(content, encoding="utf-8")
            version_ids.append(document.document_version_id)
        return GraphRAGInputManifest(workspace_id, input_root, tuple(sorted(version_ids)))

    def _safe_normalized_path(self, value: str | None) -> Path:
        if not value:
            raise ValueError("normalized document path is required")
        path = Path(value)
        candidate = path.resolve() if path.is_absolute() else (self.data_root / path).resolve()
        if candidate != self.data_root and self.data_root not in candidate.parents:
            raise ValueError("normalized document path escapes the data root")
        return candidate
