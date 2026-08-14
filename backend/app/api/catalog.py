import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Chunk,
    Document,
    DocumentVersion,
    GraphRagState,
    LogicalDocument,
    WorkflowRun,
    Workspace,
    WorkspaceIndexState,
)
from .workspaces import get_session, lookup

router = APIRouter(tags=["catalog"])


class DocumentRead(BaseModel):
    id: str
    workspace_id: str
    title: str
    active_version_id: str | None
    created_at: datetime
    updated_at: datetime
    version_number: int | None = None
    source_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    state: str | None = None
    ingestion_state: str | None = None


class DocumentDetail(DocumentRead):
    chunk_count: int
    normalized_content: str | None


class WorkspaceOverview(BaseModel):
    workspace_id: str
    document_count: int
    chunk_count: int
    dense_state: str
    sparse_state: str
    graphrag_state: str
    pending_graph_documents: int


class DashboardDocument(DocumentRead):
    workspace_name: str


class DashboardOverview(BaseModel):
    workspace_count: int
    document_count: int
    chunk_count: int
    recent_documents: list[DashboardDocument]


def ingestion_states(session: Session, workspace_id: str) -> dict[str, str]:
    states: dict[str, str] = {}
    runs = session.scalars(
        select(WorkflowRun)
        .where(
            WorkflowRun.workspace_id == workspace_id,
            WorkflowRun.job_type == "ingestion",
            WorkflowRun.deleted_at.is_(None),
        )
        .order_by(WorkflowRun.updated_at.desc())
    ).all()
    for run in runs:
        try:
            version_id = json.loads(run.payload_json or "{}").get("document_version_id")
        except json.JSONDecodeError:
            continue
        if isinstance(version_id, str):
            states.setdefault(version_id, run.state)
    return states


def document_read(
    document: Document,
    version: DocumentVersion | None,
    ingestion_state: str | None = None,
) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        active_version_id=document.active_version_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        version_number=version.version_number if version else None,
        source_filename=version.source_filename if version else None,
        mime_type=version.mime_type if version else None,
        size_bytes=version.size_bytes if version else None,
        state=version.state if version else None,
        ingestion_state=ingestion_state,
    )


@router.get("/overview", response_model=DashboardOverview)
def overview(session: Session = Depends(get_session)):
    workspace_count = session.scalar(
        select(func.count()).select_from(Workspace).where(Workspace.deleted_at.is_(None))
    ) or 0
    document_count = session.scalar(
        select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
    ) or 0
    chunk_count = session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.deleted_at.is_(None))
    ) or 0
    recent = session.execute(
        select(Document, Workspace, DocumentVersion)
        .join(Workspace, Workspace.id == Document.workspace_id)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.active_version_id)
        .where(Document.deleted_at.is_(None), Workspace.deleted_at.is_(None))
        .order_by(Document.updated_at.desc()).limit(6)
    ).all()
    return {
        "workspace_count": workspace_count,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "recent_documents": [
            DashboardDocument(
                **document_read(document, version).model_dump(), workspace_name=workspace.name
            )
            for document, workspace, version in recent
        ],
    }


@router.get("/workspaces/{workspace_id}/overview", response_model=WorkspaceOverview)
def workspace_overview(workspace_id: str, session: Session = Depends(get_session)):
    lookup(session, workspace_id)
    document_count = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
    ) or 0
    chunk_count = session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.workspace_id == workspace_id, Chunk.deleted_at.is_(None))
    ) or 0
    index = session.get(WorkspaceIndexState, workspace_id)
    graph = session.get(GraphRagState, workspace_id)
    return WorkspaceOverview(
        workspace_id=workspace_id,
        document_count=document_count,
        chunk_count=chunk_count,
        dense_state=index.dense_state if index else "empty",
        sparse_state=index.sparse_state if index else "empty",
        graphrag_state=graph.state if graph else "not_indexed",
        pending_graph_documents=graph.pending_document_count if graph else 0,
    )


@router.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentRead])
def list_documents(workspace_id: str, session: Session = Depends(get_session)):
    lookup(session, workspace_id)
    rows = session.execute(
        select(Document, DocumentVersion)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.active_version_id)
        .where(Document.workspace_id == workspace_id, Document.deleted_at.is_(None))
        .order_by(Document.updated_at.desc())
    ).all()
    states = ingestion_states(session, workspace_id)
    return [
        document_read(document, version, states.get(version.id) if version else None)
        for document, version in rows
    ]


@router.get("/workspaces/{workspace_id}/documents/{document_id}", response_model=DocumentDetail)
def document_detail(workspace_id: str, document_id: str, session: Session = Depends(get_session)):
    lookup(session, workspace_id)
    row = session.execute(
        select(Document, DocumentVersion)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.active_version_id)
        .where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
    ).first()
    if not row:
        raise HTTPException(404, "document not found")
    document, version = row
    count = session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.document_id == document.id, Chunk.deleted_at.is_(None))
    ) or 0
    content = None
    if version and version.normalized_path:
        try:
            content = Path(version.normalized_path).read_text(encoding="utf-8")
        except OSError:
            content = None
    if content is None and version:
        logical_contents = session.scalars(
            select(LogicalDocument.normalized_content)
            .where(
                LogicalDocument.workspace_id == workspace_id,
                LogicalDocument.document_version_id == version.id,
                LogicalDocument.deleted_at.is_(None),
            )
            .order_by(LogicalDocument.ordinal)
        ).all()
        if logical_contents:
            content = "\n\n".join(logical_contents)
    return DocumentDetail(
        **document_read(
            document,
            version,
            ingestion_states(session, workspace_id).get(version.id) if version else None,
        ).model_dump(),
        chunk_count=count,
        normalized_content=content,
    )
