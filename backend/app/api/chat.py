import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chat.service import (
    ask,
    backfill_default_conversation_titles,
    create_conversation,
    delete_conversation,
    edit_message,
    require_conversation,
)
from ..core.config import get_settings
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
    plan: dict[str, object] | None = None
    retrieval_queries: list[str] = Field(default_factory=list)


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
    try:
        _, answer, run = ask(session, workspace_id, conversation_id, payload.content, payload.mode)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    graph_job = bool(json.loads(answer.metadata_json or "{}").get("graphrag_query_job"))
    if graph_job:
        # Commit the durable request before the worker reads it, then wait only for the bounded
        # synchronous chat window. The API never imports or executes GraphRAG itself.
        session.commit()
        try:
            from ..workers.broker import execute_graphrag_query

            execute_graphrag_query.send(run.id)
        except Exception:
            answer.status = "failed"
            answer.content = "GraphRAG worker is unavailable."
            metadata = json.loads(answer.metadata_json or "{}")
            metadata.update(
                {
                    "fallback_reason": "worker_unavailable",
                    "termination_reason": "worker_unavailable",
                }
            )
            answer.metadata_json = json.dumps(metadata)
            run.state = "failed"
            session.commit()
            return message_read(answer)
        deadline = time.monotonic() + get_settings().graphrag_query_wait_seconds
        while time.monotonic() < deadline:
            session.expire_all()
            completed = session.get(QueryRun, run.id)
            if completed and completed.state in {"completed", "failed", "cancelled"}:
                final = session.scalar(
                    select(Message).where(
                        Message.query_run_id == run.id, Message.role == "assistant"
                    )
                )
                if final:
                    return message_read(final)
            time.sleep(0.1)
        session.expire_all()
        timed_out = session.get(QueryRun, run.id)
        if timed_out and timed_out.state in {"queued", "running"}:
            timed_out.state = "timed_out"
            answer.status = "failed"
            answer.content = "GraphRAG query timed out."
            metadata = json.loads(answer.metadata_json or "{}")
            metadata.update({"fallback_reason": "timeout", "termination_reason": "timeout"})
            answer.metadata_json = json.dumps(metadata)
            session.commit()
        return message_read(answer)
    # Commit the evidence snapshot before synchronous provider synthesis. This preserves the
    # no-network-inside-transaction boundary while returning the final answer immediately.
    if get_settings().answer_provider == "openai":
        session.commit()
        try:
            from ..chat.execution import synthesize_with_openai

            synthesize_with_openai(run.id, SessionLocal)
            session.expire_all()
            final = session.scalar(
                select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
            )
            if final:
                answer = final
        except Exception as exc:
            from ..chat.execution import record_synthesis_failure

            session.rollback()
            record_synthesis_failure(
                session,
                run.id,
                get_settings().answer_provider,
                get_settings().answer_model,
                exc,
            )
            session.commit()
    try:
        from ..workers.broker import summarize_conversation

        summarize_conversation.send(conversation_id)
    except Exception:
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
        plan=metadata.get("query_plan"),
        retrieval_queries=metadata.get("retrieval_queries", []),
    )
