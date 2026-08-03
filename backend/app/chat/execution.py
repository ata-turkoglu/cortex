"""Worker-owned provider synthesis; no network call occurs inside a database transaction."""

import asyncio
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Conversation, Message, QueryRun
from ..providers.openai import OpenAIProvider


def synthesis_snapshot(session: Session, query_run_id: str) -> tuple[str, str] | None:
    run = session.get(QueryRun, query_run_id)
    if not run or not run.conversation_id:
        return None
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
    )
    if not assistant or not assistant.citations_json or assistant.citations_json == "[]":
        return None
    citations = json.loads(assistant.citations_json)
    instruction = (
        "Answer only from the supplied evidence. Do not add external knowledge or unsupported "
        "claims. Preserve citation markers [1], [2], etc. If evidence is insufficient, say so."
    )
    evidence = assistant.content
    conversation = session.get(Conversation, run.conversation_id)
    memory = (
        f"Conversation memory:\n{conversation.summary}\n\n"
        if conversation and conversation.summary
        else ""
    )
    return (
        instruction,
        f"{memory}Question: {run.query_text}\n\nEvidence:\n{evidence}\n\nCitations: {citations}",
    )


def budget_allows_synthesis(session: Session, query_run_id: str) -> bool:
    """Pause queued provider work after a configured daily soft budget is consumed."""
    limit = get_settings().daily_soft_budget_usd
    if limit <= 0:
        return True
    spent = float(
        session.execute(
            text(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM usage_records "
                "WHERE created_at >= date('now')"
            )
        ).scalar_one()
    )
    if spent < limit:
        return True
    run = session.get(QueryRun, query_run_id)
    if run:
        run.route_reason = (
            f"{run.route_reason or ''} Provider synthesis paused: daily soft budget reached."
        ).strip()
    return False


def apply_synthesis(
    session: Session, query_run_id: str, text: str, input_tokens: int, output_tokens: int
) -> None:
    run = session.get(QueryRun, query_run_id)
    if not run or not text.strip():
        return
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
    )
    if not assistant:
        return
    assistant.content = text.strip()
    metadata = json.loads(assistant.metadata_json or "{}")
    metadata["provider_synthesis"] = "openai"
    metadata["inference"] = True
    assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)
    run.input_tokens += input_tokens
    run.output_tokens += output_tokens
    settings = get_settings()
    estimated_cost = (
        input_tokens * settings.openai_input_cost_per_1k_usd
        + output_tokens * settings.openai_output_cost_per_1k_usd
    ) / 1000
    run.estimated_cost_usd += estimated_cost
    metadata["estimated_cost_usd"] = estimated_cost
    assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)


def synthesize_with_openai(query_run_id: str, session_factory) -> None:
    """Read snapshot, call the network, then persist—each DB operation is short-lived."""
    session: Session = session_factory()
    try:
        snapshot = synthesis_snapshot(session, query_run_id)
        allowed = budget_allows_synthesis(session, query_run_id)
        session.commit()
    finally:
        session.close()
    if not snapshot or not allowed or not OpenAIProvider().configured():
        return
    generated = asyncio.run(OpenAIProvider().generate("gpt-5.6-luna", *snapshot))
    session = session_factory()
    try:
        apply_synthesis(
            session, query_run_id, generated.text, generated.input_tokens, generated.output_tokens
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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
    provider = OpenAIProvider()
    if not provider.configured():
        return
    transcript = "\n".join(
        f"{message.role}: {message.content[:500]}" for message in reversed(messages)
    )
    generated = asyncio.run(
        provider.generate(
            "gpt-5.6-luna",
            "Create a concise factual conversation memory. Do not introduce external facts.",
            transcript,
        )
    )
    session = session_factory()
    try:
        conversation = session.get(Conversation, conversation_id)
        if conversation:
            conversation.summary = generated.text.strip() or conversation.summary
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
