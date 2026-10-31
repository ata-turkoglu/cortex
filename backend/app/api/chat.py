import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..accounting import totals as usage_totals
from ..core.database import SessionLocal
from ..models import (
    Chunk,
    Conversation,
    Document,
    DocumentVersion,
    LogicalDocument,
    Message,
    QueryRun,
)
from ..query.conversation_service import (
    backfill_default_conversation_titles,
    create_conversation,
    delete_conversation,
    edit_message,
    require_conversation,
)
from ..query.production_chat import execute_v2_chat

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["chat"])
logger = logging.getLogger(__name__)


def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=255)


class ConversationRead(BaseModel):
    id: str
    workspace_id: str
    title: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AskRequest(BaseModel):
    content: str = Field(min_length=1)
    mode: str = "automatic"


class MessageEdit(BaseModel):
    content: str = Field(min_length=1)


class CitationRead(BaseModel):
    document_id: str
    document_version_id: str
    chunk_id: str
    label: str


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    status: str
    citations: list[CitationRead]
    metadata: dict[str, object]
    created_at: datetime


class QueryDebug(BaseModel):
    id: str
    routes: list[str]
    reason: str | None
    confidence: float | None
    answer_state: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    usage: dict[str, object]
    plan: dict[str, object] | None = None
    retrieval_queries: list[str] = Field(default_factory=list)
    completeness: dict[str, object] | None = None


def message_read(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        citations=json.loads(message.citations_json or "[]"),
        metadata=json.loads(message.metadata_json or "{}"),
        created_at=message.created_at,
    )


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(  # noqa: B008
    workspace_id: str,
    session: Session = Depends(get_session),  # noqa: B008
):
    conversations = session.scalars(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
    ).all()
    backfill_default_conversation_titles(session, conversations)
    return conversations


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create(  # noqa: B008
    workspace_id: str,
    payload: ConversationCreate,
    session: Session = Depends(get_session),  # noqa: B008
):
    try:
        return create_conversation(session, workspace_id, payload.title)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    workspace_id: str,
    conversation_id: str,
    session: Session = Depends(get_session),  # noqa: B008
):
    try:
        delete_conversation(session, workspace_id, conversation_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def messages(  # noqa: B008
    workspace_id: str,
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),  # noqa: B008
):
    try:
        require_conversation(session, workspace_id, conversation_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return [
        message_read(item)
        for item in session.scalars(
            select(Message)
            .where(Message.workspace_id == workspace_id, Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 100))
        ).all()
    ]


@router.post("/conversations/{conversation_id}/messages", response_model=MessageRead)
def query(  # noqa: B008
    workspace_id: str,
    conversation_id: str,
    payload: AskRequest,
    session: Session = Depends(get_session),  # noqa: B008
):
    # A sync endpoint runs in FastAPI's threadpool. V2 mixes provider awaits with
    # synchronous SQLite, Qdrant, and BM25 work, so it gets a private event loop there
    # instead of blocking the server loop for every other request.
    try:
        _, answer, _ = asyncio.run(
            execute_v2_chat(session, workspace_id, conversation_id, payload.content, payload.mode)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        from ..workers.broker import summarize_conversation

        summarize_conversation.send(conversation_id)
    except Exception:
        # Summaries are best-effort; the answer is already persisted.
        logger.warning(
            "Conversation summary was not enqueued for conversation_id=%s",
            conversation_id,
            exc_info=True,
        )
    return message_read(answer)


@router.patch("/conversations/{conversation_id}/messages/{message_id}", response_model=MessageRead)
def edit(  # noqa: B008
    workspace_id: str,
    conversation_id: str,
    message_id: str,
    payload: MessageEdit,
    session: Session = Depends(get_session),  # noqa: B008
):
    try:
        return message_read(
            edit_message(session, workspace_id, conversation_id, message_id, payload.content)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sources/{chunk_id}")
def source_details(  # noqa: B008
    workspace_id: str,
    chunk_id: str,
    session: Session = Depends(get_session),  # noqa: B008
):
    row = session.execute(
        select(Chunk, Document, DocumentVersion, LogicalDocument)
        .join(Document, Document.id == Chunk.document_id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .outerjoin(LogicalDocument, LogicalDocument.id == Chunk.logical_document_id)
        .where(Chunk.id == chunk_id, Chunk.workspace_id == workspace_id)
    ).first()
    if not row:
        raise HTTPException(404, "source chunk not found in workspace")
    chunk, document, version, logical = row
    return {
        "chunk_id": chunk.id,
        "content": chunk.content,
        "document_id": logical.id if logical else document.id,
        "document_code": logical.document_code if logical else None,
        "document_title": logical.title if logical else document.title,
        "source_document_id": document.id,
        "source_original": logical.source_original if logical else version.source_filename,
        "page_start": logical.page_start if logical else None,
        "page_end": logical.page_end if logical else None,
        "document_version_id": version.id,
        "version_number": version.version_number,
    }


@router.get("/query-runs/{query_run_id}", response_model=QueryDebug)
def debug(  # noqa: B008
    workspace_id: str,
    query_run_id: str,
    session: Session = Depends(get_session),  # noqa: B008
):
    run = session.scalar(
        select(QueryRun).where(QueryRun.id == query_run_id, QueryRun.workspace_id == workspace_id)
    )
    if not run:
        raise HTTPException(404, "query run not found in workspace")
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
    )
    metadata = json.loads(assistant.metadata_json or "{}") if assistant else {}
    usage = usage_totals(session, workspace_id=workspace_id, query_run_id=run.id)
    return QueryDebug(
        id=run.id,
        routes=json.loads(run.selected_routes_json or "[]"),
        reason=run.route_reason,
        confidence=run.route_confidence,
        answer_state=run.answer_state,
        latency_ms=run.latency_ms,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        estimated_cost_usd=float(usage["cost"]) if usage["cost"] is not None else None,
        usage=usage,
        plan=metadata.get("query_plan"),
        retrieval_queries=metadata.get("retrieval_queries", []),
        completeness=json.loads(run.completeness_json) if run.completeness_json else None,
    )
