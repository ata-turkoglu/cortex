"""Neutral conversation persistence helpers shared by the V2 production API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Message, Workspace

DEFAULT_CONVERSATION_TITLE = "New conversation"
CONVERSATION_TITLE_LIMIT = 72


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
        title=title.strip() or DEFAULT_CONVERSATION_TITLE,
        summary=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(conversation)
    return conversation


def delete_conversation(session: Session, workspace_id: str, conversation_id: str) -> None:
    conversation = require_conversation(session, workspace_id, conversation_id)
    timestamp = datetime.now(UTC)
    conversation.deleted_at = timestamp
    conversation.updated_at = timestamp


def conversation_title_from_query(content: str) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= CONVERSATION_TITLE_LIMIT:
        return normalized
    return f"{normalized[: CONVERSATION_TITLE_LIMIT - 1].rstrip()}…"


def backfill_default_conversation_titles(
    session: Session, conversations: list[Conversation]
) -> None:
    pending = {item.id: item for item in conversations if item.title == DEFAULT_CONVERSATION_TITLE}
    if not pending:
        return
    messages = session.scalars(
        select(Message)
        .where(Message.conversation_id.in_(pending), Message.role == "user")
        .order_by(Message.conversation_id, Message.created_at)
    )
    for message in messages:
        conversation = pending.pop(message.conversation_id, None)
        if conversation:
            conversation.title = conversation_title_from_query(message.content)
        if not pending:
            break


def edit_message(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    message_id: str,
    content: str,
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
    message.content = content.strip()
    message.edited_at = timestamp
    message.updated_at = timestamp
    return message
