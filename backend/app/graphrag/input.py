"""Materialize workspace-normalized documents for a deferred GraphRAG index run."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, DocumentVersion, LogicalDocument


@dataclass(frozen=True)
class GraphRAGInputManifest:
    workspace_id: str
    input_root: Path
    document_version_ids: tuple[str, ...]
    logical_document_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphRAGInputDocument:
    document_version_id: str
    normalized_path: Path
    logical_document_id: str | None = None
    document_code: str | None = None
    title: str | None = None
    document_type: str | None = None
    source_original: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    normalized_content: str | None = None


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
        logical_rows = session.scalars(
            select(LogicalDocument)
            .join(Document, Document.id == LogicalDocument.source_document_id)
            .where(
                LogicalDocument.workspace_id == workspace_id,
                LogicalDocument.deleted_at.is_(None),
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
                LogicalDocument.document_version_id == Document.active_version_id,
            )
            .order_by(LogicalDocument.source_document_id, LogicalDocument.ordinal)
        ).all()
        if logical_rows:
            return tuple(
                GraphRAGInputDocument(
                    document_version_id=item.document_version_id,
                    normalized_path=Path(),
                    logical_document_id=item.id,
                    document_code=item.document_code,
                    title=item.title,
                    document_type=item.document_type,
                    source_original=item.source_original,
                    page_start=item.page_start,
                    page_end=item.page_end,
                    normalized_content=item.normalized_content,
                )
                for item in logical_rows
            )
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
        # The directory is a generated snapshot. Remove prior Markdown inputs so a source-level
        # file from an older run cannot be indexed alongside its new logical-document files.
        for stale_input in input_root.glob("*.md"):
            stale_input.unlink()
        version_ids: list[str] = []
        logical_ids: list[str] = []
        for document in documents:
            identity = document.logical_document_id or document.document_version_id
            target = input_root / f"{identity}.md"
            content = (
                document.normalized_content
                if document.normalized_content is not None
                else document.normalized_path.read_text(encoding="utf-8")
            )
            if document.logical_document_id:
                metadata = (
                    f"# {document.document_code}\n\n"
                    f"Logical document ID: {document.logical_document_id}\n\n"
                    f"Title: {document.title}\n\n"
                    f"Document type: {document.document_type}\n\n"
                    f"Source original: {document.source_original}\n\n"
                    f"Pages: {document.page_start or ''}-{document.page_end or ''}\n\n"
                )
                content = metadata + content
                logical_ids.append(document.logical_document_id)
            target.write_text(content, encoding="utf-8")
            version_ids.append(document.document_version_id)
        return GraphRAGInputManifest(
            workspace_id,
            input_root,
            tuple(sorted(set(version_ids))),
            tuple(sorted(logical_ids)),
        )

    def _safe_normalized_path(self, value: str | None) -> Path:
        if not value:
            raise ValueError("normalized document path is required")
        path = Path(value)
        candidate = path.resolve() if path.is_absolute() else (self.data_root / path).resolve()
        if candidate != self.data_root and self.data_root not in candidate.parents:
            raise ValueError("normalized document path escapes the data root")
        return candidate
