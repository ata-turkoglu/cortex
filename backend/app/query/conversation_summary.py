"""Worker-owned conversation memory summary; no network call runs inside a transaction."""

import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..accounting import persist_usage, usage_from_generated
from ..core.config import get_settings
from ..models import Conversation, Message
from ..providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


def summarize_conversation_with_openai(conversation_id: str, session_factory) -> None:
    """Summarize old conversational context only after the configured memory window is exceeded."""
    session: Session = session_factory()
    try:
        conversation = session.get(Conversation, conversation_id)
        if not conversation:
            return
        messages = session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(get_settings().conversation_memory_window_messages + 1)
        ).all()
    finally:
        session.close()
    if len(messages) <= get_settings().conversation_memory_window_messages:
        return
    if get_settings().summary_provider != "openai":
        # Only the OpenAI text adapter is implemented for summaries. Never send the
        # transcript to a provider other than the one the user assigned.
        logger.info(
            "Conversation summary skipped: provider %s is not supported",
            get_settings().summary_provider,
        )
        return
    provider = OpenAIProvider()
    if not provider.configured():
        return
    transcript = "\n".join(
        f"{message.role}: {message.content[:500]}" for message in reversed(messages)
    )
    generated = asyncio.run(
        provider.generate(
            get_settings().summary_model,
            "Create a concise factual conversation memory. Do not introduce external facts.",
            transcript,
        )
    )
    session = session_factory()
    try:
        conversation = session.get(Conversation, conversation_id)
        if conversation:
            conversation.summary = generated.text.strip() or conversation.summary
            persist_usage(
                session,
                workspace_id=conversation.workspace_id,
                stage="conversation_summary",
                provider="openai",
                model=get_settings().summary_model,
                usage=usage_from_generated(generated),
                idempotency_key=(
                    f"conversation_summary:{conversation_id}:{generated.request_id or uuid4()}"
                ),
                provider_request_id=generated.request_id,
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
