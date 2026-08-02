import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.uploads import UploadValidationError, store_upload
from ..core.workspaces import WorkspaceContext, WorkspaceNotFoundError
from ..ingestion.parsers import DocumentParseError, parse_to_markdown
from ..ingestion.chunking import chunk_markdown
from ..ingestion.folders import resolve_folder_path
from ..ingestion.workflow import create_ingestion_run
from ..models import Chunk, ChunkRelationship, Document, DocumentVersion
from ..models import DocumentMetadata
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
        raise HTTPException(status_code=422, detail="a replacement request accepts exactly one file")
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
    uploaded = []
    for upload in files:
        content = await upload.read(settings.upload_max_bytes + 1)
        try:
            source_hash = hashlib.sha256(content).hexdigest()
            duplicate = session.scalar(
                select(DocumentVersion.id).where(
                    DocumentVersion.workspace_id == workspace_id,
                    DocumentVersion.source_hash == source_hash,
                )
            )
            if duplicate:
                raise HTTPException(status_code=409, detail="identical document content already exists")
            stored = store_upload(
                context.resource_path("uploads"),
                upload.filename or "",
                upload.content_type,
                content,
                settings.upload_max_bytes,
            )
            parsed = parse_to_markdown(stored.storage_path, stored.original_filename)
            normalized_root = context.resource_path("normalized")
            normalized_root.mkdir(parents=True, exist_ok=True)
            normalized_path = normalized_root / f"{uuid4().hex}.md"
            normalized_path.write_text(parsed.markdown, encoding="utf-8", newline="\n")
        except UploadValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DocumentParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await upload.close()
        now = datetime.now(timezone.utc)
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
        for key, value in {
            "filename": stored.original_filename,
            "mime_type": stored.media_type,
            "source_sha256": stored.sha256,
            "size_bytes": stored.size_bytes,
        }.items():
            session.add(
                DocumentMetadata(
                    id=str(uuid4()), workspace_id=workspace_id, document_id=document.id,
                    document_version_id=version.id, key=key, value_json=json.dumps(value),
                    origin="system", created_at=now, updated_at=now,
                )
            )
        chunk_rows = []
        for draft in chunk_markdown(
            parsed.markdown, settings.chunk_token_limit, settings.chunk_overlap_tokens
        ):
            chunk = Chunk(
                id=str(uuid4()),
                workspace_id=workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=draft.ordinal,
                content=draft.content,
                content_hash=hashlib.sha256(draft.content.encode()).hexdigest(),
                metadata_json=json.dumps({"heading": draft.heading}, ensure_ascii=False),
                created_at=now,
            )
            chunk_rows.append(chunk)
        session.add_all(chunk_rows)
        for previous, following in zip(chunk_rows, chunk_rows[1:]):
            session.add(
                ChunkRelationship(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    source_chunk_id=previous.id,
                    target_chunk_id=following.id,
                    relationship_type="next",
                )
            )
        workflow_run = create_ingestion_run(session, workspace_id, version.id)
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
                "workflow_run_id": workflow_run.id,
            }
        )
    return {"uploads": uploaded}
