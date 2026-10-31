from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Conversation, Message, Workspace
from app.query.context import (
    ContextEntityReference,
    ContextRevisionConflict,
    ConversationContextState,
    load_conversation_context,
    save_conversation_context,
)


def _session():
    return sessionmaker(bind=create_engine("sqlite:///:memory:"))()


def _conversation(session, workspace_id: str, *, title: str = "Conversation") -> Conversation:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        title=title,
        created_at=now,
        updated_at=now,
    )
    session.add(conversation)
    return conversation


def _workspace(session, name: str) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()),
        slug=f"{name}-{uuid4()}",
        name=name,
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    return workspace


def test_context_is_durable_bounded_and_revision_checked():
    session = _session()
    Base.metadata.create_all(session.bind)
    workspace = _workspace(session, "A")
    conversation = _conversation(session, workspace.id)
    now = datetime.now(UTC)
    messages = []
    for offset, content in enumerate(("one", "two", "three")):
        message = Message(
            id=str(uuid4()),
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            role="user",
            content=content,
            status="complete",
            created_at=now + timedelta(seconds=offset),
            updated_at=now + timedelta(seconds=offset),
        )
        messages.append(message)
        session.add(message)
    session.commit()

    state = ConversationContextState(
        resolved_entities=(
            ContextEntityReference(
                mention="Hasan Tahsin Merter",
                entity_type="person",
                resolution="resolved",
                canonical_entity_id="person-1",
                display_name="Hasan Tahsin Merter",
                source_message_id=messages[-1].id,
            ),
        )
    )
    assert (
        save_conversation_context(
            session, workspace.id, conversation.id, state, expected_revision=0
        )
        == 1
    )
    session.commit()

    snapshot = load_conversation_context(session, workspace.id, conversation.id, history_limit=2)
    assert snapshot.revision == 1
    assert [item.content for item in snapshot.history] == ["two", "three"]
    assert snapshot.state.resolved_entities[0].canonical_entity_id == "person-1"
    with pytest.raises(ContextRevisionConflict):
        save_conversation_context(
            session, workspace.id, conversation.id, state, expected_revision=0
        )


def test_context_rejects_cross_workspace_conversation_and_message_sources():
    session = _session()
    Base.metadata.create_all(session.bind)
    workspace_a = _workspace(session, "A")
    workspace_b = _workspace(session, "B")
    conversation_a = _conversation(session, workspace_a.id)
    conversation_b = _conversation(session, workspace_b.id)
    now = datetime.now(UTC)
    foreign_message = Message(
        id=str(uuid4()),
        workspace_id=workspace_b.id,
        conversation_id=conversation_b.id,
        role="user",
        content="foreign",
        status="complete",
        created_at=now,
        updated_at=now,
    )
    session.add(foreign_message)
    session.commit()

    with pytest.raises(LookupError):
        load_conversation_context(session, workspace_a.id, conversation_b.id, history_limit=2)
    state = ConversationContextState(
        resolved_entities=(
            ContextEntityReference(
                mention="foreign",
                resolution="resolved",
                canonical_entity_id="person-2",
                source_message_id=foreign_message.id,
            ),
        )
    )
    with pytest.raises(ValueError, match="source messages"):
        save_conversation_context(session, workspace_a.id, conversation_a.id, state)
