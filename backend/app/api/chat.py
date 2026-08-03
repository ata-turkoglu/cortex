import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chat.service import ask, create_conversation, edit_message, require_conversation
from ..core.database import SessionLocal
from ..models import Chunk, Conversation, Document, DocumentVersion, Message, QueryRun

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["chat"])


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
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


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
    return session.scalars(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
    ).all()


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
    try:
        _, answer, run = ask(session, workspace_id, conversation_id, payload.content, payload.mode)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        from ..workers.broker import execute_query_synthesis, summarize_conversation

        execute_query_synthesis.send(run.id)
        summarize_conversation.send(conversation_id)
    except Exception:
        # The grounded local response remains available when Redis is absent.
        pass
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
        select(Chunk, Document, DocumentVersion)
        .join(Document, Document.id == Chunk.document_id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(Chunk.id == chunk_id, Chunk.workspace_id == workspace_id)
    ).first()
    if not row:
        raise HTTPException(404, "source chunk not found in workspace")
    chunk, document, version = row
    return {
        "chunk_id": chunk.id,
        "content": chunk.content,
        "document_id": document.id,
        "document_title": document.title,
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
    return QueryDebug(
        id=run.id,
        routes=json.loads(run.selected_routes_json or "[]"),
        reason=run.route_reason,
        confidence=run.route_confidence,
        answer_state=run.answer_state,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
    )
