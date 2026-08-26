"""V2-only production chat adapter with short durable transactions."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.embedding_runtime import build_production_embedder
from ..models import (
    Conversation,
    Message,
    QueryRun,
    QueryRuntimeActivation,
    QueryStepRun,
)
from ..workflows.queries import create_query_run
from .context import ContextCanonicalResultSet, save_conversation_context
from .conversation_service import (
    DEFAULT_CONVERSATION_TITLE,
    conversation_title_from_query,
    require_conversation,
)
from .production import V2QueryServiceFactory
from .service import V2QueryServiceResult
from .understanding import evolve_context_state
from .understanding.planner import SemanticPlannerOutputError

MODES = {"automatic", "document_search", "deep_analysis"}
logger = logging.getLogger(__name__)


async def execute_v2_chat(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    content: str,
    mode: str,
    *,
    factory: V2QueryServiceFactory | None = None,
) -> tuple[Message, Message, QueryRun]:
    """Persist a request, execute detached V2, then persist its final result."""
    if factory is None:
        # Host API processes must use the same persisted global runtime settings
        # as workers before creating their cached provider adapters.
        configuration, provider = build_production_embedder(session)
        selected_factory = V2QueryServiceFactory(
            settings=get_settings(),
            embedding_configuration=configuration,
            embedding_provider=provider,
            canonical_session=session,
        )
    else:
        selected_factory = factory
    started = time.perf_counter()
    user, run, inputs = _begin(
        session,
        workspace_id,
        conversation_id,
        content,
        mode,
        selected_factory,
    )
    user_id, run_id = user.id, run.id
    session.commit()
    try:
        result = await selected_factory.build(inputs).execute_inputs(
            session, content.strip(), inputs
        )
    except Exception as error:
        logger.exception(
            "Query V2 execution failed for run_id=%s workspace_id=%s error=%s",
            run_id,
            workspace_id,
            error,
        )
        session.rollback()
        assistant = _persist_failure(
            session,
            workspace_id,
            conversation_id,
            run_id,
            inputs.generation_scope.generation_id,
            error,
            started,
        )
        session.commit()
        return session.get(Message, user_id), assistant, session.get(QueryRun, run_id)
    assistant = _persist_result(session, conversation_id, run_id, result, started)
    session.flush()
    final_entity_result = _final_entity_result(result, assistant.id)
    save_conversation_context(
        session,
        workspace_id,
        conversation_id,
        evolve_context_state(
            inputs.conversation_context,
            result.prepared.semantic.understanding,
            source_message_id=assistant.id,
            final_entity_result=final_entity_result,
        ),
        expected_revision=inputs.conversation_context.revision,
    )
    session.commit()
    return session.get(Message, user_id), assistant, session.get(QueryRun, run_id)


def _begin(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    content: str,
    mode: str,
    factory: V2QueryServiceFactory,
):
    if mode not in MODES or not content.strip():
        raise ValueError("a query and supported mode are required")
    activation = session.get(QueryRuntimeActivation, workspace_id)
    if activation is None or activation.runtime_version != "v2" or not activation.generation_id:
        raise RuntimeError("workspace has no validated V2 production generation")
    conversation = require_conversation(session, workspace_id, conversation_id)
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
        metadata_json=json.dumps({"runtime": "v2"}),
        edited_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(user)
    if conversation.title == DEFAULT_CONVERSATION_TITLE:
        conversation.title = conversation_title_from_query(content)
    conversation.updated_at = timestamp
    run = create_query_run(session, workspace_id, content.strip(), conversation_id)
    run.state = "running"
    run.selected_routes_json = json.dumps(["v2"])
    run.route_reason = "query_v2_physical_plan"
    run.updated_at = timestamp
    session.flush()
    _set_step(session, run.id, "route", "completed")
    _set_step(session, run.id, "retrieve", "running")
    inputs = factory.context_loader.load(session, workspace_id, conversation_id)
    if inputs.generation_scope.generation_id != activation.generation_id:
        raise RuntimeError("V2 request scope differs from the validated production generation")
    return user, run, inputs


def _persist_result(
    session: Session,
    conversation_id: str,
    run_id: str,
    result: V2QueryServiceResult,
    started: float,
) -> Message:
    run = session.get(QueryRun, run_id)
    conversation = session.get(Conversation, conversation_id)
    if run is None or conversation is None:
        raise RuntimeError("V2 query persistence state disappeared")
    timestamp = datetime.now(UTC)
    trace = asdict(result.trace)
    citations = [dict(item) for item in result.answer.citations]
    retrieval_capabilities = [
        step.capability
        for step in (
            result.prepared.physical_plan.graph.steps if result.prepared.physical_plan.graph else ()
        )
        if step.engine == "retrieval"
    ]
    run.state = "completed"
    run.selected_routes_json = json.dumps(["v2", *retrieval_capabilities])
    run.route_confidence = result.prepared.semantic.understanding.confidence
    run.answer_state = result.answer.state
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.updated_at = timestamp
    _set_step(session, run.id, "retrieve", "completed")
    _set_step(session, run.id, "synthesize", "completed")
    assistant = Message(
        id=str(uuid4()),
        workspace_id=run.workspace_id,
        conversation_id=conversation_id,
        query_run_id=run.id,
        role="assistant",
        content=result.answer.content,
        status="completed",
        citations_json=json.dumps(citations, ensure_ascii=False),
        metadata_json=json.dumps(
            {
                "runtime": "v2",
                "query_run_id": run.id,
                "generation_id": result.trace.generation_id,
                "embedding_config_hash": result.trace.embedding_config_hash,
                "answer_state": result.answer.state,
                "execution_trace": trace,
                "query_plan": result.prepared.physical_plan.model_dump(mode="json"),
                "logical_ir": result.prepared.logical_ir.model_dump(mode="json"),
                "semantic_state": result.prepared.semantic.understanding.state,
                "semantic_planner_tier": result.prepared.semantic.selected_tier,
                "reasoning_package_generation": result.package.generation_id,
                "retrieval_queries": [run.query_text],
                "citation_summary": {
                    "cited_evidence_count": len(citations),
                    "user_visible_source_count": len(citations),
                },
                **result.answer.metadata,
            },
            ensure_ascii=False,
        ),
        edited_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(assistant)
    conversation.updated_at = timestamp
    return assistant


def _persist_failure(
    session: Session,
    workspace_id: str,
    conversation_id: str,
    run_id: str,
    generation_id: str,
    error: Exception,
    started: float,
) -> Message:
    run = session.get(QueryRun, run_id)
    conversation = session.get(Conversation, conversation_id)
    if run is None or conversation is None:
        raise RuntimeError("V2 query failure state disappeared") from error
    timestamp = datetime.now(UTC)
    planner_output_invalid = isinstance(error, SemanticPlannerOutputError)
    run.state = "completed" if planner_output_invalid else "failed"
    run.answer_state = "unsupported"
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.updated_at = timestamp
    _set_step(session, run.id, "retrieve", "failed")
    _set_step(session, run.id, "synthesize", "failed")
    assistant = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query_run_id=run.id,
        role="assistant",
        content=_failure_content(error),
        status="completed" if planner_output_invalid else "failed",
        citations_json="[]",
        metadata_json=json.dumps(
            {
                "runtime": "v2",
                "query_run_id": run.id,
                "generation_id": generation_id,
                "answer_state": "unsupported",
                "failure_type": type(error).__name__,
                **(
                    {"failure_reason": "semantic_planner_output_invalid"}
                    if isinstance(error, SemanticPlannerOutputError)
                    else {}
                ),
                "fallback_used": False,
            }
        ),
        edited_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(assistant)
    conversation.updated_at = timestamp
    return assistant


def _failure_content(error: Exception) -> str:
    """Keep validation failures fail-closed without exposing provider diagnostics."""
    if isinstance(error, SemanticPlannerOutputError):
        return (
            "I couldn't safely interpret this request. Please rephrase it with the "
            "people, relationship, and ordering rule stated explicitly."
        )
    return "The V2 query could not be completed safely."


def _set_step(session: Session, run_id: str, name: str, state: str) -> None:
    step = session.scalar(
        select(QueryStepRun).where(
            QueryStepRun.query_run_id == run_id, QueryStepRun.step_name == name
        )
    )
    if step:
        step.state = state
        step.updated_at = datetime.now(UTC)


def _final_entity_result(
    result: V2QueryServiceResult, source_message_id: str
) -> ContextCanonicalResultSet | None:
    """Persist only one final, same-generation canonical entity set for referents."""
    if (
        not result.package.generation_id
        or result.package.generation_id != result.trace.generation_id
        or not result.package.entities
    ):
        return None
    entity_types = {item.entity_type for item in result.package.entities}
    if len(entity_types) != 1:
        return None
    entity_ids = tuple(dict.fromkeys(item.entity_id for item in result.package.entities))
    return ContextCanonicalResultSet(
        canonical_entity_ids=entity_ids,
        entity_type=next(iter(entity_types)),
        generation_id=result.package.generation_id,
        source_message_id=source_message_id,
    )
