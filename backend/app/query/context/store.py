"""Short-transaction persistence for durable Query V2 conversation context."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Conversation, ConversationContextRecord, Message
from .schemas import (
    CONTEXT_SCHEMA_VERSION,
    ConversationContext,
    ConversationContextState,
    ConversationTurn,
)


class ContextRevisionConflict(RuntimeError):
    pass


def _require_conversation(
    session: Session, workspace_id: str, conversation_id: str
) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise LookupError("conversation not found in workspace")
    return conversation


def load_conversation_context(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    *,
    history_limit: int,
) -> ConversationContext:
    """Load a detached snapshot; callers close the transaction before provider work."""
    if history_limit < 1:
        raise ValueError("history_limit must be positive")
    conversation = _require_conversation(session, workspace_id, conversation_id)
    record = session.scalar(
        select(ConversationContextRecord).where(
            ConversationContextRecord.workspace_id == workspace_id,
            ConversationContextRecord.conversation_id == conversation_id,
        )
    )
    rows = list(
        session.scalars(
            select(Message)
            .where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(history_limit)
        )
    )
    state = (
        ConversationContextState.model_validate_json(record.state_json)
        if record
        else ConversationContextState()
    )
    return ConversationContext(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        revision=record.revision if record else 0,
        summary=conversation.summary,
        history=tuple(
            ConversationTurn(
                message_id=item.id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
            )
            for item in reversed(rows)
        ),
        state=state,
    )


def save_conversation_context(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    state: ConversationContextState,
    *,
    expected_revision: int | None = None,
) -> int:
    """Persist validated state without committing or making any external call."""
    _require_conversation(session, workspace_id, conversation_id)
    source_ids = {
        item.source_message_id
        for collection in (
            state.resolved_entities,
            state.candidate_references,
            state.temporal_focus,
            state.explicit_constraints,
            state.assumptions,
        )
        for item in collection
        if item.source_message_id
    }
    if source_ids:
        valid_ids = set(
            session.scalars(
                select(Message.id).where(
                    Message.workspace_id == workspace_id,
                    Message.conversation_id == conversation_id,
                    Message.id.in_(source_ids),
                )
            )
        )
        if valid_ids != source_ids:
            raise ValueError("context source messages must belong to the workspace conversation")

    record = session.scalar(
        select(ConversationContextRecord).where(
            ConversationContextRecord.workspace_id == workspace_id,
            ConversationContextRecord.conversation_id == conversation_id,
        )
    )
    current_revision = record.revision if record else 0
    if expected_revision is not None and expected_revision != current_revision:
        raise ContextRevisionConflict(
            f"context revision changed: expected {expected_revision}, found {current_revision}"
        )
    now = datetime.now(UTC)
    payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    if record is None:
        record = ConversationContextRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            schema_version=CONTEXT_SCHEMA_VERSION,
            revision=1,
            state_json=payload,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
    else:
        record.schema_version = CONTEXT_SCHEMA_VERSION
        record.revision += 1
        record.state_json = payload
        record.updated_at = now
    session.flush()
    return record.revision
