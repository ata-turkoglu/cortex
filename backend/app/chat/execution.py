"""Worker-owned provider synthesis; no network call occurs inside a database transaction."""

import asyncio
import json
import logging
import re

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Chunk, Conversation, Message, QueryRun
from ..providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)
_WORD = re.compile(r"[\wÇĞİÖŞÜçğıöşü]+", re.UNICODE)
_CITATION = re.compile(r"\[(\d+)\]")


def finalize_citations(
    answer: str, citations: list[dict[str, str]]
) -> tuple[str, list[dict[str, str]]] | None:
    """Validate, prune, and densely renumber the user-visible final citation set."""
    markers = [int(value) for value in _CITATION.findall(answer)]
    if not markers or any(index < 1 or index > len(citations) for index in markers):
        return None
    old_to_new: dict[int, int] = {}
    final: list[dict[str, str]] = []
    for index in markers:
        if index not in old_to_new:
            old_to_new[index] = len(final) + 1
            item = citations[index - 1]
            key = (item.get("document_id", ""), item.get("chunk_id", ""))
            if not any(
                (existing.get("document_id", ""), existing.get("chunk_id", "")) == key
                for existing in final
            ):
                final.append(item)
            else:
                old_to_new[index] = next(
                    position
                    for position, existing in enumerate(final, 1)
                    if (existing.get("document_id", ""), existing.get("chunk_id", "")) == key
                )
    rendered = _CITATION.sub(lambda match: f"[{old_to_new[int(match.group(1))]}]", answer)
    return rendered, final


def citation_summary(
    metadata: dict[str, object], final_citations: list[dict[str, str]]
) -> dict[str, int]:
    selection = metadata.get("evidence_selection", {})
    selected = (
        int(selection.get("selected_count", len(final_citations)))
        if isinstance(selection, dict)
        else len(final_citations)
    )
    return {
        "retrieval_candidate_count": (
            int(selection.get("input_count", selected)) if isinstance(selection, dict) else selected
        ),
        "selected_evidence_count": selected,
        "cited_evidence_count": len(final_citations),
        "user_visible_source_count": len(final_citations),
        "unused_selected_evidence_count": max(0, selected - len(final_citations)),
    }


def raw_evidence_guard(answer: str, evidence: list[str]) -> bool:
    """Detect a conservative long contiguous copied-token span from a source chunk."""
    answer_tokens = _WORD.findall(answer.casefold())
    if len(answer_tokens) < 12:
        return False
    for source in evidence:
        source_tokens = _WORD.findall(source.casefold())
        for start in range(len(answer_tokens)):
            for source_start in range(len(source_tokens)):
                length = 0
                while (
                    start + length < len(answer_tokens)
                    and source_start + length < len(source_tokens)
                    and answer_tokens[start + length] == source_tokens[source_start + length]
                ):
                    length += 1
                if length >= 12:
                    return True
    return False


def _selected_evidence(session: Session, assistant: Message) -> list[str]:
    citations = json.loads(assistant.citations_json or "[]")
    ids = [item.get("chunk_id") for item in citations if item.get("chunk_id")]
    if not ids:
        return []
    rows = session.scalars(
        select(Chunk).where(Chunk.workspace_id == assistant.workspace_id, Chunk.id.in_(ids))
    ).all()
    by_id = {item.id: item.content for item in rows}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def record_synthesis_unavailable(session: Session, query_run_id: str, error_code: str) -> None:
    """Record why a normal answer kept its deterministic fallback."""
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == query_run_id, Message.role == "assistant")
    )
    if not assistant:
        return
    metadata = json.loads(assistant.metadata_json or "{}")
    synthesis = metadata.get("synthesis", {})
    if not synthesis.get("eligible"):
        return
    synthesis.update(
        {"attempted": False, "success": False, "fallback_used": True, "error_code": error_code}
    )
    metadata["synthesis"] = synthesis
    assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)


def record_synthesis_failure(
    session: Session, query_run_id: str, provider: str, model: str, error: Exception
) -> None:
    """Persist a safe diagnostic record without provider payloads or credentials."""
    run = session.get(QueryRun, query_run_id)
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == query_run_id, Message.role == "assistant")
    )
    if not run or not assistant:
        return
    error_type = type(error).__name__
    metadata = json.loads(assistant.metadata_json or "{}")
    metadata["synthesis"] = {
        "eligible": True,
        "attempted": True,
        "success": False,
        "provider": provider,
        "model": model,
        "error_type": error_type,
        "error_code": "provider_request_failed",
        "failure_stage": "synchronous_answer_synthesis",
        "fallback_used": True,
        "raw_evidence_guard_triggered": False,
        "regeneration_attempted": False,
    }
    assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)
    logger.warning(
        "Synchronous synthesis failed query_run_id=%s provider=%s model=%s error_type=%s",
        query_run_id,
        provider,
        model,
        error_type,
    )


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
    metadata = json.loads(assistant.metadata_json or "{}")
    if metadata.get("graphrag_final_answer"):
        return None
    if metadata.get("intent") == "entity_document_lookup":
        return None
    plan = metadata.get("query_plan", {})
    operation = plan.get("operation", "generic_qa")
    max_words = {
        "identify": get_settings().identify_answer_max_words,
        "describe": get_settings().describe_answer_max_words,
        "timeline": get_settings().timeline_answer_max_words,
    }.get(operation, 400)
    instruction = (
        "Answer the user's question directly in the user's language, using only the supplied "
        "evidence. Paraphrase facts; never reproduce or dump raw evidence text, source blocks, "
        "retrieval metadata, or internal headings. Attach supplied [1], [2] markers after the "
        "sentence or clause they support. Preserve uncertainty, omit unsupported facts, and do "
        f"not claim complete inventories or verified totals. Keep under {max_words} words."
    )
    if operation == "describe":
        instruction += (
            " For describe answers, synthesize the most informative supported facts from distinct "
            "selected evidence; prefer specific dates, roles, properties, locations, identifiers, "
            "and shares over a vague category-only summary. Historical records do not establish "
            "current ownership. Every factual sentence needs an allowed citation."
        )
    evidence = _selected_evidence(session, assistant)
    if not evidence:
        return None
    conversation = session.get(Conversation, run.conversation_id)
    memory = (
        f"Conversation memory:\n{conversation.summary}\n\n"
        if conversation and conversation.summary
        else ""
    )
    return (
        instruction,
        f"{memory}Question: {run.query_text}\n\nValidated query plan: "
        f"{json.dumps(metadata.get('query_plan', {}), ensure_ascii=False)}\n\n"
        f"Selected evidence:\n{json.dumps(evidence, ensure_ascii=False)}\n\nCitations: {citations}",
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
    session: Session,
    query_run_id: str,
    text: str,
    input_tokens: int,
    output_tokens: int,
    *,
    raw_evidence_guard_triggered: bool = False,
    regeneration_attempted: bool = False,
) -> None:
    run = session.get(QueryRun, query_run_id)
    if not run or not text.strip():
        return
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
    )
    if not assistant:
        return
    metadata = json.loads(assistant.metadata_json or "{}")
    original_citations = json.loads(assistant.citations_json or "[]")
    finalized = finalize_citations(text.strip(), original_citations)
    if not finalized:
        raise ValueError("invalid_or_missing_citations")
    assistant.content, final_citations = finalized
    assistant.citations_json = json.dumps(final_citations, ensure_ascii=False)
    metadata["provider_synthesis"] = "openai"
    metadata["inference"] = True
    metadata["synthesis"] = {
        "eligible": True,
        "attempted": True,
        "success": True,
        "provider": "openai",
        "model": get_settings().answer_model,
        "fallback_used": False,
        "raw_evidence_guard_triggered": raw_evidence_guard_triggered,
        "regeneration_attempted": regeneration_attempted,
    }
    metadata["citation_summary"] = citation_summary(metadata, final_citations)
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
    if not snapshot:
        return
    settings = get_settings()
    if not allowed:
        session = session_factory()
        try:
            record_synthesis_unavailable(session, query_run_id, "budget_paused")
            session.commit()
        finally:
            session.close()
        return
    if settings.answer_provider != "openai" or not OpenAIProvider().configured():
        session = session_factory()
        try:
            record_synthesis_unavailable(session, query_run_id, "provider_unavailable")
            session.commit()
        finally:
            session.close()
        return
    generated = asyncio.run(OpenAIProvider().generate(settings.answer_model, *snapshot))
    encoded_evidence = snapshot[1].split("Selected evidence:\n", 1)[1].split("\n\nCitations:", 1)[0]
    evidence = json.loads(encoded_evidence)
    guard_triggered = raw_evidence_guard(generated.text, evidence)
    citation_retry = (
        finalize_citations(generated.text, json.loads(snapshot[1].rsplit("Citations: ", 1)[1]))
        is None
    )
    regenerated = False
    if guard_triggered or citation_retry:
        retry = asyncio.run(
            OpenAIProvider().generate(
                settings.answer_model,
                f"{snapshot[0]} Rewrite concisely. Do not quote or copy evidence text. "
                "Use only valid supplied citation markers for every factual claim.",
                snapshot[1],
            )
        )
        regenerated = True
        if (
            raw_evidence_guard(retry.text, evidence)
            or finalize_citations(retry.text, json.loads(snapshot[1].rsplit("Citations: ", 1)[1]))
            is None
        ):
            raise RuntimeError("synthesis_guard_rejected")
        generated = retry
    session = session_factory()
    try:
        apply_synthesis(
            session,
            query_run_id,
            generated.text,
            generated.input_tokens,
            generated.output_tokens,
            raw_evidence_guard_triggered=guard_triggered,
            regeneration_attempted=regenerated,
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
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
