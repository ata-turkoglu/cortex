from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Message, Workspace
from app.query.conversation_service import (
    DEFAULT_CONVERSATION_TITLE,
    backfill_default_conversation_titles,
    conversation_title_from_query,
    create_conversation,
    delete_conversation,
)


def _session_with_workspace():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    timestamp, workspace_id = datetime.now(UTC), str(uuid4())
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
    session.commit()
    return session, workspace_id


def test_conversation_title_from_query_is_compact():
    title = conversation_title_from_query("kelime " * 20)

    assert len(title) == 72
    assert title.endswith("…")
    assert conversation_title_from_query("  Ankara'nın   nüfusu nedir?  ") == (
        "Ankara'nın nüfusu nedir?"
    )


def test_default_titles_are_backfilled_from_the_first_user_message():
    session, workspace_id = _session_with_workspace()
    conversation = create_conversation(session, workspace_id, DEFAULT_CONVERSATION_TITLE)
    timestamp = datetime.now(UTC)
    session.add(
        Message(
            id=str(uuid4()),
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            query_run_id=None,
            role="user",
            content="Ankara nedir?",
            status="completed",
            citations_json=None,
            metadata_json=None,
            edited_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.flush()

    backfill_default_conversation_titles(session, [conversation])

    assert conversation.title == "Ankara nedir?"


def test_conversation_delete_is_soft_and_workspace_scoped():
    session, workspace_id = _session_with_workspace()
    conversation = create_conversation(session, workspace_id, "Silinecek sohbet")

    delete_conversation(session, workspace_id, conversation.id)

    assert conversation.deleted_at is not None
    assert conversation.updated_at == conversation.deleted_at


def test_summary_never_sends_the_transcript_to_an_unassigned_provider(monkeypatch):
    from app.core.config import get_settings
    from app.query import conversation_summary

    session, workspace_id = _session_with_workspace()
    conversation = create_conversation(session, workspace_id, "Özet")
    timestamp = datetime.now(UTC)
    for index in range(3):
        session.add(
            Message(
                id=str(uuid4()),
                workspace_id=workspace_id,
                conversation_id=conversation.id,
                query_run_id=None,
                role="user",
                content=f"Soru {index}",
                status="completed",
                citations_json=None,
                metadata_json=None,
                edited_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    session.commit()
    monkeypatch.setattr(get_settings(), "conversation_memory_window_messages", 1)
    monkeypatch.setattr(get_settings(), "summary_provider", "ollama")

    class ForbiddenOpenAI:
        def __init__(self):
            raise AssertionError("transcript must not reach OpenAI")

    monkeypatch.setattr(conversation_summary, "OpenAIProvider", ForbiddenOpenAI)

    conversation_summary.summarize_conversation_with_openai(conversation.id, lambda: session)

    assert session.get(type(conversation), conversation.id).summary is None


def test_summary_usage_is_recorded_with_the_conversation_workspace(monkeypatch):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models import UsageEvent
    from app.providers.base import GeneratedText
    from app.query import conversation_summary

    session, workspace_id = _session_with_workspace()
    conversation = create_conversation(session, workspace_id, "Özet")
    timestamp = datetime.now(UTC)
    for index in range(3):
        session.add(
            Message(
                id=str(uuid4()),
                workspace_id=workspace_id,
                conversation_id=conversation.id,
                query_run_id=None,
                role="user",
                content=f"Soru {index}",
                status="completed",
                citations_json=None,
                metadata_json=None,
                edited_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    session.commit()
    monkeypatch.setattr(get_settings(), "conversation_memory_window_messages", 1)
    monkeypatch.setattr(get_settings(), "summary_provider", "openai")
    monkeypatch.setattr(get_settings(), "summary_model", "gpt-5.6-luna")

    class FakeOpenAI:
        def configured(self):
            return True

        async def generate(self, model, instructions, input_text):
            return GeneratedText(
                "Kısa özet", input_tokens=100, output_tokens=20, request_id="req-1"
            )

    monkeypatch.setattr(conversation_summary, "OpenAIProvider", FakeOpenAI)

    conversation_summary.summarize_conversation_with_openai(conversation.id, lambda: session)

    event = session.scalars(select(UsageEvent)).one()
    assert (event.workspace_id, event.stage, event.input_tokens) == (
        workspace_id,
        "conversation_summary",
        100,
    )
    assert session.get(type(conversation), conversation.id).summary == "Kısa özet"
