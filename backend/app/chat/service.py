"""Safe deterministic router and evidence-first synthesis for the chat API.

Provider-backed selector/synthesis can replace these adapters without changing the persisted
query contract. Until then no model is called and answers are limited to stored evidence.
"""

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Chunk, Conversation, Document, Message, QueryRun, QueryStepRun, Workspace
from ..retrieval.schemas import AnswerState, Evidence
from ..workflows.queries import create_query_run

MODES = {"automatic", "document_search", "deep_analysis"}
ROUTES = {"hybrid", "graphrag_local", "graphrag_global", "graphrag_drift"}


@dataclass(frozen=True)
class RouteSelection:
    routes: tuple[str, ...]
    reason: str
    confidence: float


def select_routes(query: str, mode: str) -> RouteSelection:
    """Selector behavior, deliberately constrained to approved V1 combinations."""
    normalized = query.casefold()
    if mode == "document_search":
        return RouteSelection(("hybrid",), "Document Search mode requires Hybrid Search.", 1.0)
    if mode == "deep_analysis":
        return RouteSelection(
            ("hybrid", "graphrag_global"),
            "Deep Analysis combines document evidence with graph-wide context.",
            0.82,
        )
    if any(term in normalized for term in ("overview", "pattern", "across", "genel", "ilişki")):
        return RouteSelection(
            ("hybrid", "graphrag_global"), "The question requests cross-document context.", 0.76
        )
    return RouteSelection(("hybrid",), "The question is best answered from document passages.", 0.9)


def _step(session: Session, run: QueryRun, name: str, state: str) -> None:
    item = session.scalar(
        select(QueryStepRun).where(
            QueryStepRun.query_run_id == run.id, QueryStepRun.step_name == name
        )
    )
    if item:
        item.state, item.updated_at = state, datetime.now(UTC)


def _evidence(session: Session, workspace_id: str, query: str, limit: int = 5) -> list[Evidence]:
    terms = [term for term in query.casefold().split() if len(term) > 2]
    rows = session.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.deleted_at.is_(None),
            Document.deleted_at.is_(None),
        )
        .order_by(Chunk.ordinal)
    ).all()
    ranked = []
    for chunk, document in rows:
        score = sum(chunk.content.casefold().count(term) for term in terms)
        if score:
            ranked.append((score, chunk, document))
    return [
        Evidence(
            workspace_id=workspace_id,
            source=document.title,
            content=chunk.content,
            score=float(score),
            document_id=document.id,
            document_version_id=chunk.document_version_id,
            chunk_id=chunk.id,
            citation_label=f"{document.title}, passage {chunk.ordinal + 1}",
        )
        for score, chunk, document in sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]
    ]


def _answer(evidence: list[Evidence]) -> tuple[str, AnswerState, list[dict[str, str]]]:
    if not evidence:
        return (
            "Bu çalışma alanındaki kaynaklarda bu soruyu destekleyen kanıt bulamadım.",
            AnswerState.UNSUPPORTED,
            [],
        )
    citations = [
        {
            "document_id": item.document_id or "",
            "document_version_id": item.document_version_id or "",
            "chunk_id": item.chunk_id or "",
            "label": item.citation_label or item.source,
        }
        for item in evidence
    ]
    limit = {"concise": 280, "balanced": 700, "detailed": 1400}[get_settings().answer_style]
    excerpts = "\n\n".join(
        f"[{index}] {item.content.strip()[:limit]}" for index, item in enumerate(evidence, 1)
    )
    return (f"Kaynaklardaki ilgili kanıtlar:\n\n{excerpts}", AnswerState.GROUNDED, citations)


def require_conversation(session: Session, workspace_id: str, conversation_id: str) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise LookupError("conversation not found in workspace")
    return conversation


def create_conversation(session: Session, workspace_id: str, title: str) -> Conversation:
    if not session.scalar(
        select(Workspace.id).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    ):
        raise LookupError("workspace not found")
    timestamp = datetime.now(UTC)
    conversation = Conversation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        title=title.strip() or "New conversation",
        summary=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(conversation)
    return conversation


def edit_message(
    session: Session, workspace_id: str, conversation_id: str, message_id: str, content: str
) -> Message:
    require_conversation(session, workspace_id, conversation_id)
    message = session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
    )
    if not message:
        raise LookupError("user message not found in workspace conversation")
    if not content.strip():
        raise ValueError("message content is required")
    timestamp = datetime.now(UTC)
    message.content, message.edited_at, message.updated_at = content.strip(), timestamp, timestamp
    return message


def ask(
    session: Session, workspace_id: str, conversation_id: str, content: str, mode: str
) -> tuple[Message, Message, QueryRun]:
    if mode not in MODES or not content.strip():
        raise ValueError("a query and supported mode are required")
    conversation = require_conversation(session, workspace_id, conversation_id)
    started = time.perf_counter()
    timestamp = datetime.now(UTC)
    user = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_run_id=None,
        role="user",
        content=content.strip(),
        status="completed",
        citations_json=None,
        metadata_json=None,
        edited_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(user)
    recent = session.scalars(
        select(Message)
        .where(Message.workspace_id == workspace_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(get_settings().conversation_memory_window_messages)
    ).all()
    memory = [{"role": item.role, "content": item.content[:500]} for item in reversed(recent)]
    run = create_query_run(session, workspace_id, content, conversation_id)
    _step(session, run, "route", "running")
    # Import lazily to keep the deterministic service usable in minimal worker environments.
    from .router import LlamaIndexRouter

    choice = LlamaIndexRouter().select(content, mode)
    run.selected_routes_json, run.route_reason, run.route_confidence = (
        json.dumps(choice.routes),
        choice.reason,
        choice.confidence,
    )
    _step(session, run, "route", "completed")
    _step(session, run, "retrieve", "running")
    evidence = _evidence(session, workspace_id, content)
    # Graph routes are intentionally unavailable until their upstream results can be normalized.
    # Hybrid evidence is retained as a safe fallback rather than fabricating graph evidence.
    if len(choice.routes) > 1:
        run.route_reason += (
            " Graph route is unavailable or stale; Hybrid Search was used as the safe fallback."
        )
    _step(session, run, "retrieve", "completed")
    _step(session, run, "synthesize", "running")
    answer, answer_state, citations = _answer(evidence)
    run.answer_state, run.state, run.latency_ms = (
        answer_state.value,
        "completed",
        int((time.perf_counter() - started) * 1000),
    )
    run.updated_at = datetime.now(UTC)
    _step(session, run, "synthesize", "completed")
    assistant = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_run_id=run.id,
        role="assistant",
        content=answer,
        status="completed",
        citations_json=json.dumps(citations, ensure_ascii=False),
        metadata_json=json.dumps(
            {
                "query_run_id": run.id,
                "route_reason": run.route_reason,
                "confidence": choice.confidence,
                "answer_state": answer_state.value,
                "memory_message_count": len(memory),
                "inference": False,
            }
        ),
        edited_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(assistant)
    conversation.updated_at = datetime.now(UTC)
    return user, assistant, run
