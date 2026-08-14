"""Worker-owned execution of a durable GraphRAG chat query."""

import json
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.settings_service import load_runtime_settings
from ..core.workspaces import WorkspaceContext
from ..graphrag.adapter import GraphRAGAdapter, GraphRoute
from ..graphrag.reporting import record_stage_usage
from ..models import Message, QueryRun, QueryStepRun
from ..retrieval.schemas import AnswerState


def _step(session: Session, run: QueryRun, name: str, state: str) -> None:
    step = session.scalar(
        select(QueryStepRun).where(
            QueryStepRun.query_run_id == run.id, QueryStepRun.step_name == name
        )
    )
    if step:
        step.state, step.updated_at = state, datetime.now(UTC)


def execute(session: Session, query_run_id: str) -> bool:
    """Run only in the GraphRAG worker image; API code never imports this module."""
    load_runtime_settings(session)
    run = session.get(QueryRun, query_run_id)
    if not run or run.state != "queued":
        return False
    assistant = session.scalar(
        select(Message).where(Message.query_run_id == run.id, Message.role == "assistant")
    )
    if not assistant:
        raise RuntimeError("GraphRAG query is missing its assistant message")
    metadata = json.loads(assistant.metadata_json or "{}")
    requested = str(metadata.get("requested_route") or "")
    if requested not in {"graphrag_local", "graphrag_global", "graphrag_drift"}:
        raise ValueError("invalid GraphRAG query route")
    route = GraphRoute(requested.removeprefix("graphrag_"))
    settings = get_settings()
    layer = f"graphrag_{route.value}"
    provider, model = getattr(settings, f"{layer}_provider"), getattr(settings, f"{layer}_model")
    started = time.perf_counter()
    run.state = "running"
    _step(session, run, "retrieve", "running")
    try:
        context = WorkspaceContext.load(session, run.workspace_id)
        if context.graphrag_state.state != "ready":
            raise RuntimeError("graph_not_indexed")
        if route is GraphRoute.DRIFT:
            possible_calls = (
                settings.graphrag_drift_n_depth * settings.graphrag_drift_k_followups + 2
            )
            if possible_calls > settings.graphrag_drift_max_llm_calls:
                raise RuntimeError("budget_limit")
        # Do not hold SQLite's write transaction while the external GraphRAG CLI runs.
        session.commit()
        adapter = GraphRAGAdapter(
            run.workspace_id, context.graph_root, config_path=context.graph_root / "settings.yaml"
        )
        result = adapter.query(route, run.query_text)
        session.refresh(run)
        session.refresh(assistant)
        # The API's bounded wait may have made this run terminal while GraphRAG was executing.
        # Preserve that terminal outcome rather than replacing it with a late answer.
        if run.state != "running":
            return True
        if not result.evidence:
            raise RuntimeError(result.fallback_reason or "graphrag_no_result")
        citations = [
            {
                "document_id": item.document_id or "",
                "document_version_id": item.document_version_id or "",
                "chunk_id": item.chunk_id or "",
                "label": item.citation_label or item.source,
            }
            for item in result.evidence
        ]
        duration_ms = int((time.perf_counter() - started) * 1000)
        metadata.update({
            "executed_route": requested,
            "provider": provider,
            "model": model,
            "graphrag_search_mode": route.value,
            "graphrag_final_answer": True,
            "fallback_used": False,
            "duration_ms": duration_ms,
            "termination_reason": "completed",
        })
        assistant.content, assistant.status, assistant.citations_json = (
            "\n\n".join(item.content for item in result.evidence),
            "completed",
            json.dumps(citations, ensure_ascii=False),
        )
        assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        run.answer_state, run.state, run.latency_ms = (
            AnswerState.GROUNDED.value,
            "completed",
            duration_ms,
        )
        _step(session, run, "retrieve", "completed")
        _step(session, run, "synthesize", "completed")
        record_stage_usage(
            session,
            run.workspace_id,
            stage=requested,
            provider=provider,
            model=model,
            request_count=1,
            duration_ms=duration_ms,
            query_run_id=run.id,
        )
    except Exception as exc:
        reason = str(exc)
        if settings.graphrag_query_fallback_to_hybrid:
            # A fallback is opt-in: the same worker produces a normal evidence-backed answer
            # instead of invoking GraphRAG a second time or asking the API to execute it.
            from ..chat.service import _answer, _hybrid_evidence

            fallback = _hybrid_evidence(
                session, run.workspace_id, run.query_text, needs_list=False
            )
            fallback_evidence = list(fallback.evidence)
            fallback_answer, _, fallback_citations = _answer(fallback_evidence)
            if fallback_citations:
                metadata.update(
                    {
                        "executed_route": "hybrid",
                        "fallback_used": True,
                        "fallback_reason": reason,
                        "termination_reason": "hybrid_fallback",
                        "retrieval": fallback.trace.as_dict(),
                    }
                )
                assistant.content, assistant.status, assistant.citations_json = (
                    fallback_answer,
                    "completed",
                    json.dumps(fallback_citations, ensure_ascii=False),
                )
                assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)
                run.answer_state, run.state = fallback.state.value, "completed"
                _step(session, run, "retrieve", "completed")
                _step(session, run, "synthesize", "completed")
                run.updated_at = datetime.now(UTC)
                return True
        metadata.update(
            {"executed_route": None, "fallback_reason": reason, "termination_reason": reason}
        )
        assistant.content, assistant.status, assistant.citations_json = (
            "GraphRAG query could not be completed.",
            "failed",
            "[]",
        )
        assistant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        run.answer_state, run.state = AnswerState.UNSUPPORTED.value, "failed"
        _step(session, run, "retrieve", "failed")
        _step(session, run, "synthesize", "failed")
    run.updated_at = datetime.now(UTC)
    return True
