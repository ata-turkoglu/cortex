from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.execution import synthesis_snapshot
from app.chat.service import (
    DEFAULT_CONVERSATION_TITLE,
    RouteSelection,
    ask,
    backfill_default_conversation_titles,
    conversation_title_from_query,
    create_conversation,
    delete_conversation,
    select_routes,
)
from app.core.config import get_settings
from app.models import Base, Chunk, Document, DocumentVersion, Message, Workspace
from app.retrieval.hybrid import result_for
from app.retrieval.schemas import Evidence
from app.workflows.graphrag_query import execute as execute_graphrag_query


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


def test_first_question_replaces_the_default_conversation_title():
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, DEFAULT_CONVERSATION_TITLE)

    ask(session, workspace_id, conversation.id, "  Ankara'nın   nüfusu nedir?  ", "automatic")

    assert conversation.title == "Ankara'nın nüfusu nedir?"


def test_conversation_title_from_query_is_compact():
    title = conversation_title_from_query("kelime " * 20)

    assert len(title) == 72
    assert title.endswith("…")


def test_default_titles_are_backfilled_from_legacy_conversations():
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, DEFAULT_CONVERSATION_TITLE)
    ask(session, workspace_id, conversation.id, "Ankara nedir?", "automatic")
    conversation.title = DEFAULT_CONVERSATION_TITLE

    backfill_default_conversation_titles(session, [conversation])

    assert conversation.title == "Ankara nedir?"


def test_conversation_delete_is_soft_and_workspace_scoped():
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Silinecek sohbet")

    delete_conversation(session, workspace_id, conversation.id)

    assert conversation.deleted_at is not None
    assert conversation.updated_at == conversation.deleted_at


def test_router_only_selects_approved_routes():
    assert select_routes("belgeler arası genel ilişki", "automatic").routes == (
        "hybrid",
        "graphrag_global",
    )


def test_graphrag_route_creates_a_worker_owned_query_job(monkeypatch):
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Graph")
    monkeypatch.setattr(
        "app.chat.router.LlamaIndexRouter.select",
        lambda *_: RouteSelection(("graphrag_local",), "Graph route", 1.0),
    )
    _, answer, run = ask(session, workspace_id, conversation.id, "Ankara", "automatic")

    assert answer.status == "queued"
    assert run.state == "queued"
    assert '"requested_route": "graphrag_local"' in answer.metadata_json
    assert synthesis_snapshot(session, run.id) is None


def test_graphrag_worker_writes_the_final_answer_without_synthesis(monkeypatch, tmp_path):
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Graph")
    monkeypatch.setattr(
        "app.chat.router.LlamaIndexRouter.select",
        lambda *_: RouteSelection(("graphrag_global",), "Graph route", 1.0),
    )
    _, answer, run = ask(session, workspace_id, conversation.id, "Ankara?", "automatic")
    calls: list[tuple[str, str]] = []

    class FakeAdapter:
        def __init__(self, workspace_id, graph_root, *, config_path):
            assert workspace_id == run.workspace_id
            assert graph_root == tmp_path
            assert config_path == tmp_path / "settings.yaml"

        def query(self, route, query):
            calls.append((route.value, query))
            return result_for(
                [Evidence(workspace_id, "graphrag:global", "Native GraphRAG answer", 1.0)],
            )

    monkeypatch.setattr(
        "app.workflows.graphrag_query.WorkspaceContext.load",
        lambda *_: SimpleNamespace(
            graph_root=tmp_path, graphrag_state=SimpleNamespace(state="ready")
        ),
    )
    monkeypatch.setattr("app.workflows.graphrag_query.GraphRAGAdapter", FakeAdapter)

    assert execute_graphrag_query(session, run.id) is True
    assert calls == [("global", "Ankara?")]
    assert run.state == "completed"
    assert answer.content == "Native GraphRAG answer"
    assert '"graphrag_final_answer": true' in answer.metadata_json
    assert synthesis_snapshot(session, run.id) is None


def test_graphrag_worker_uses_hybrid_only_when_the_policy_is_enabled(monkeypatch, tmp_path):
    session, workspace_id = session_with_documents()
    conversation = create_conversation(session, workspace_id, "Graph")
    monkeypatch.setattr(
        "app.chat.router.LlamaIndexRouter.select",
        lambda *_: RouteSelection(("graphrag_local",), "Graph route", 1.0),
    )
    _, answer, run = ask(session, workspace_id, conversation.id, "Ankara", "automatic")
    monkeypatch.setattr(get_settings(), "graphrag_query_fallback_to_hybrid", True)
    monkeypatch.setattr(
        "app.workflows.graphrag_query.WorkspaceContext.load",
        lambda *_: SimpleNamespace(
            graph_root=tmp_path, graphrag_state=SimpleNamespace(state="stale")
        ),
    )

    assert execute_graphrag_query(session, run.id) is True
    assert run.state == "completed"
    assert answer.status == "completed"
    assert '"executed_route": "hybrid"' in answer.metadata_json
    assert '"fallback_used": true' in answer.metadata_json
