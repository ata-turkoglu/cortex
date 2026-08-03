from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.service import ask, create_conversation, select_routes
from app.models import Base, Chunk, Document, DocumentVersion, Message, Workspace


def session_with_documents():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    timestamp, workspace_id, document_id, version_id = (
        datetime.now(UTC),
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
    )
    session.add(
        Workspace(
            id=workspace_id,
            slug="chat",
            name="Chat",
            state="active",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.add(
        Document(
            id=document_id,
            workspace_id=workspace_id,
            title="Ankara Notları",
            content_hash=None,
            active_version_id=version_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.add(
        DocumentVersion(
            id=version_id,
            workspace_id=workspace_id,
            document_id=document_id,
            version_number=1,
            source_hash=str(uuid4()),
            source_path="source",
            source_filename="notes.md",
            size_bytes=10,
            state="ready",
            created_at=timestamp,
        )
    )
    session.add(
        Chunk(
            id=str(uuid4()),
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=version_id,
            ordinal=0,
            content="Ankara Türkiye'nin başkentidir.",
            content_hash="content",
            created_at=timestamp,
        )
    )
    session.commit()
    return session, workspace_id


def test_chat_is_workspace_scoped_and_cites_document_version():
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Başkent")
    _, answer, run = ask(session, workspace_id, conversation.id, "Ankara nedir?", "document_search")
    assert run.selected_routes_json == '["hybrid"]'
    assert answer.citations_json and "document_version_id" in answer.citations_json
    assert session.query(Message).filter_by(workspace_id=workspace_id).count() == 2


def test_unsupported_answers_do_not_fabricate_citations():
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Boş")
    _, answer, run = ask(session, workspace_id, conversation.id, "Mars kolonisi", "automatic")
    assert run.answer_state == "unsupported"
    assert answer.citations_json == "[]"


def test_router_only_selects_approved_routes():
    assert select_routes("belgeler arası genel ilişki", "automatic").routes == (
        "hybrid",
        "graphrag_global",
    )
