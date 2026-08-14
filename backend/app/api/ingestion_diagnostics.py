"""Read-only trace of source files through logical documents, chunks, and GraphRAG."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chat.service import _hybrid_evidence
from ..core.workspaces import WorkspaceContext, WorkspaceNotFoundError
from ..graphrag.adapter import GraphRAGAdapter
from ..models import Chunk, Document, DocumentVersion, LogicalDocument
from ..retrieval.document_lookup import group_evidence_by_document
from .workspaces import get_session

router = APIRouter(tags=["ingestion-diagnostics"])


class DiagnosticChunk(BaseModel):
    id: str
    ordinal: int
    page: str | None
    heading: str | None


class DiagnosticLogicalDocument(BaseModel):
    document_id: str
    document_code: str
    title: str
    document_type: str
    source_original: str
    page_start: int | None
    page_end: int | None
    chunks: list[DiagnosticChunk]
    entities: list[str]
    graph_nodes: list[str]


class RetrievedLogicalDocument(BaseModel):
    document_id: str
    document_code: str | None
    title: str
    score: float


class IngestionDiagnostic(BaseModel):
    source_document_id: str
    source_original: str
    document_version_id: str
    logical_documents: list[DiagnosticLogicalDocument]
    retrieved_documents: list[RetrievedLogicalDocument]


def _matching_artifact_ids(
    adapter: GraphRAGAdapter, logical: LogicalDocument
) -> tuple[list[str], list[str]]:
    entities: list[str] = []
    graph_nodes: list[str] = []
    for resource_type in ("entities", "text_units"):
        for artifact in adapter.load_artifacts(resource_type):
            linked_ids = adapter.logical_document_ids_for(artifact)
            searchable = f"{artifact.text} {json.dumps(artifact.attributes)}".casefold()
            if logical.id in linked_ids or logical.document_code.casefold() in searchable:
                graph_nodes.append(f"{resource_type}:{artifact.artifact_id}")
                if resource_type == "entities":
                    entities.append(artifact.attributes.get("title") or artifact.artifact_id)
    return sorted(set(entities)), sorted(set(graph_nodes))


@router.get(
    "/workspaces/{workspace_id}/ingestion-diagnostics/{source_document_id}",
    response_model=IngestionDiagnostic,
)
def ingestion_diagnostic(  # noqa: B008
    workspace_id: str,
    source_document_id: str,
    query: str | None = Query(default=None),
    session: Session = Depends(get_session),  # noqa: B008
):
    try:
        context = WorkspaceContext.load(session, workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(404, "workspace not found") from exc
    row = session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.id == Document.active_version_id)
        .where(
            Document.id == source_document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    ).first()
    if not row:
        raise HTTPException(404, "source document not found in workspace")
    source, version = row
    logical_rows = session.scalars(
        select(LogicalDocument)
        .where(
            LogicalDocument.workspace_id == workspace_id,
            LogicalDocument.source_document_id == source.id,
            LogicalDocument.document_version_id == version.id,
            LogicalDocument.deleted_at.is_(None),
        )
        .order_by(LogicalDocument.ordinal)
    ).all()
    chunk_rows = session.scalars(
        select(Chunk)
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.document_version_id == version.id,
            Chunk.deleted_at.is_(None),
        )
        .order_by(Chunk.ordinal)
    ).all()
    chunks_by_logical: dict[str, list[DiagnosticChunk]] = {}
    for chunk in chunk_rows:
        metadata = json.loads(chunk.metadata_json or "{}")
        if chunk.logical_document_id:
            chunks_by_logical.setdefault(chunk.logical_document_id, []).append(
                DiagnosticChunk(
                    id=chunk.id,
                    ordinal=chunk.ordinal,
                    page=str(metadata.get("page")) if metadata.get("page") else None,
                    heading=metadata.get("heading"),
                )
            )
    adapter = GraphRAGAdapter(workspace_id, context.graph_root)
    logical_output = []
    for logical in logical_rows:
        entities, graph_nodes = _matching_artifact_ids(adapter, logical)
        logical_output.append(
            DiagnosticLogicalDocument(
                document_id=logical.id,
                document_code=logical.document_code,
                title=logical.title,
                document_type=logical.document_type,
                source_original=logical.source_original,
                page_start=logical.page_start,
                page_end=logical.page_end,
                chunks=chunks_by_logical.get(logical.id, []),
                entities=entities,
                graph_nodes=graph_nodes,
            )
        )
    retrieved = []
    if query:
        retrieval = _hybrid_evidence(session, workspace_id, query, needs_list=True)
        matches = group_evidence_by_document(list(retrieval.evidence), exact_text=query)
        retrieved = [
            RetrievedLogicalDocument(
                document_id=item.document_id,
                document_code=item.document_code,
                title=item.title,
                score=item.score,
            )
            for item in matches
            if any(logical.id == item.document_id for logical in logical_rows)
        ]
    return IngestionDiagnostic(
        source_document_id=source.id,
        source_original=version.source_filename,
        document_version_id=version.id,
        logical_documents=logical_output,
        retrieved_documents=retrieved,
    )
