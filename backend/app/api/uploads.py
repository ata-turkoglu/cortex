import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.uploads import UploadValidationError, store_upload
from ..core.workspaces import WorkspaceContext, WorkspaceNotFoundError
from ..ingestion.chunking import chunk_markdown
from ..ingestion.folders import resolve_folder_path
from ..ingestion.logical_documents import detect_logical_documents
from ..ingestion.metadata import metadata_extraction_assignment
from ..ingestion.parsers import DocumentParseError, parse_to_markdown
from ..ingestion.workflow import create_ingestion_run
from ..models import (
    Chunk,
    ChunkRelationship,
    Document,
    DocumentMetadata,
    DocumentVersion,
    LogicalDocument,
)
from .workspaces import get_session

router = APIRouter(prefix="/workspaces/{workspace_id}/uploads", tags=["uploads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_files(
    workspace_id: str,
    files: list[UploadFile] = File(...),
    replace_document_id: str | None = Form(default=None),
    folder_path: str | None = Form(default=None),
    session: Session = Depends(get_session),
):
    try:
        context = WorkspaceContext.load(session, workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workspace not found") from exc
    settings = get_settings()
    try:
        folder_id = resolve_folder_path(session, workspace_id, folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if replace_document_id and len(files) != 1:
        raise HTTPException(
            status_code=422, detail="a replacement request accepts exactly one file"
        )
    replacement_document = None
    if replace_document_id:
        replacement_document = session.scalar(
            select(Document).where(
                Document.id == replace_document_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
        if replacement_document is None:
            raise HTTPException(status_code=404, detail="document not found in workspace")
    # Snapshot all database-backed routing before file/Docling work.  The transaction is
    # committed so no filesystem/parser/model operation can hold SQLite locks.
    upload_root = context.resource_path("uploads")
    normalized_root = context.resource_path("normalized")
    session.commit()
    uploaded = []
    for upload in files:
        content = await upload.read(settings.upload_max_bytes + 1)
        try:
            source_hash = hashlib.sha256(content).hexdigest()
            duplicate = session.scalar(
                select(DocumentVersion.id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.workspace_id == workspace_id,
                    DocumentVersion.source_hash == source_hash,
                    DocumentVersion.deleted_at.is_(None),
                    Document.deleted_at.is_(None),
                )
            )
            if duplicate:
                raise HTTPException(
                    status_code=409, detail="identical document content already exists"
                )
            session.commit()
            stored = store_upload(
                upload_root,
                upload.filename or "",
                upload.content_type,
                content,
                settings.upload_max_bytes,
            )
            parsed = parse_to_markdown(stored.storage_path, stored.original_filename)
            logical_drafts = detect_logical_documents(
                parsed, stored.original_filename, stored.media_type
            )
            normalized_root.mkdir(parents=True, exist_ok=True)
            normalized_path = normalized_root / f"{uuid4().hex}.md"
            normalized_path.write_text(parsed.markdown, encoding="utf-8", newline="\n")
        except UploadValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DocumentParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await upload.close()
        now = datetime.now(UTC)
        if replace_document_id:
            document = replacement_document
            next_version = (
                session.scalar(
                    select(func.max(DocumentVersion.version_number)).where(
                        DocumentVersion.document_id == document.id,
                        DocumentVersion.workspace_id == workspace_id,
                    )
                )
                or 0
            ) + 1
            document.content_hash = stored.sha256
            document.updated_at = now
        else:
            document = Document(
                id=str(uuid4()),
                workspace_id=workspace_id,
                folder_id=folder_id,
                title=stored.original_filename,
                content_hash=stored.sha256,
                created_at=now,
                updated_at=now,
            )
            session.add(document)
            next_version = 1
        version = DocumentVersion(
            id=str(uuid4()),
            workspace_id=workspace_id,
            document_id=document.id,
            version_number=next_version,
            source_hash=stored.sha256,
            normalized_content_hash=parsed.content_hash,
            source_path=str(stored.storage_path),
            normalized_path=str(normalized_path),
            source_filename=stored.original_filename,
            mime_type=stored.media_type,
            size_bytes=stored.size_bytes,
            state="uploaded",
            created_at=now,
        )
        document.active_version_id = version.id
        session.add(version)
        # Document metadata, chunks, and workflow rows reference the document/version
        # rows.  Flush their parents explicitly because this session disables autoflush
        # and SQLite enforces foreign keys during each INSERT.
        try:
            session.flush()
        except IntegrityError as exc:
            # The pre-insert lookup gives a helpful result for ordinary duplicate
            # uploads. The database constraint remains the authority when a legacy
            # database has not migrated yet or concurrent requests race that lookup.
            session.rollback()
            stored.storage_path.unlink(missing_ok=True)
            normalized_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409, detail="identical document content already exists"
            ) from exc
        metadata_provider, metadata_model = metadata_extraction_assignment()
        for key, value in {
            "filename": stored.original_filename,
            "mime_type": stored.media_type,
            "source_sha256": stored.sha256,
            "size_bytes": stored.size_bytes,
            "metadata_extraction_assignment": {
                "provider": metadata_provider,
                "model": metadata_model,
            },
        }.items():
            session.add(
                DocumentMetadata(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    key=key,
                    value_json=json.dumps(value),
                    origin="system",
                    created_at=now,
                    updated_at=now,
                )
            )
        chunk_rows = []
        logical_rows = []
        chunk_ordinal = 0
        for logical_draft in logical_drafts:
            logical = LogicalDocument(
                id=str(uuid4()),
                workspace_id=workspace_id,
                source_document_id=document.id,
                document_version_id=version.id,
                ordinal=logical_draft.ordinal,
                document_code=logical_draft.document_code,
                title=logical_draft.title,
                document_type=logical_draft.document_type,
                source_original=logical_draft.source_original,
                page_start=logical_draft.page_start,
                page_end=logical_draft.page_end,
                normalized_content=logical_draft.markdown,
                created_at=now,
            )
            session.add(logical)
            session.flush()
            logical_rows.append(logical)
            for draft in chunk_markdown(
                logical_draft.markdown,
                settings.chunk_token_limit,
                settings.chunk_overlap_tokens,
            ):
                chunk = Chunk(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    logical_document_id=logical.id,
                    ordinal=chunk_ordinal,
                    content=draft.content,
                    content_hash=hashlib.sha256(draft.content.encode()).hexdigest(),
                    metadata_json=json.dumps(
                        {
                            "document_id": logical.id,
                            "source_document_id": document.id,
                            "document_code": logical.document_code,
                            "title": logical.title,
                            "page": logical.page_start or "",
                            "page_start": logical.page_start or "",
                            "page_end": logical.page_end or "",
                            "source_original": logical.source_original,
                            "document_type": logical.document_type,
                            "heading": draft.heading,
                        },
                        ensure_ascii=False,
                    ),
                    created_at=now,
                )
                chunk_rows.append(chunk)
                chunk_ordinal += 1
        session.add_all(chunk_rows)
        for previous, following in zip(chunk_rows, chunk_rows[1:], strict=False):
            if previous.logical_document_id != following.logical_document_id:
                continue
            session.add(
                ChunkRelationship(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    source_chunk_id=previous.id,
                    target_chunk_id=following.id,
                    relationship_type="next",
                )
            )
        workflow_run = create_ingestion_run(session, workspace_id, version.id, queued=True)
        uploaded.append(
            {
                "filename": stored.original_filename,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
                "media_type": stored.media_type,
                "document_id": document.id,
                "document_version_id": version.id,
                "version_number": version.version_number,
                "chunk_count": len(chunk_rows),
                "logical_document_count": len(logical_rows),
                "logical_documents": [
                    {
                        "document_id": item.id,
                        "document_code": item.document_code,
                        "title": item.title,
                        "document_type": item.document_type,
                        "source_original": item.source_original,
                        "page_start": item.page_start,
                        "page_end": item.page_end,
                    }
                    for item in logical_rows
                ],
                "workflow_run_id": workflow_run.id,
            }
        )
    # Commit before dispatching: the worker uses a separate SQLite connection and must
    # be able to read the workflow run and its durable step checkpoints immediately.
    session.commit()
    from ..workers.broker import dispatch_workflow

    for item in uploaded:
        dispatch_workflow(item["workflow_run_id"])
    return {"uploads": uploaded}
