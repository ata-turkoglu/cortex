"""Durable, worker-owned execution for a real GraphRAG reindex run."""

import asyncio
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.qdrant import get_qdrant_client
from ..core.workspaces import WorkspaceContext
from ..graphrag.adapter import GraphRAGAdapter
from ..graphrag.input import GraphRAGInputMaterializer
from ..graphrag.neo4j import sync_graph_to_neo4j
from ..graphrag.qdrant import GraphRAGQdrantAdapter, mirror_graph_outputs
from ..graphrag.reporting import record_stage_usage
from ..graphrag.updates import (
    complete_deferred_update,
    fail_deferred_update,
    prepare_deferred_update,
)
from ..models import WorkflowRun, WorkflowStepRun, WorkspaceLock
from ..providers.embeddings import OllamaEmbeddingAdapter, OpenAIEmbeddingAdapter
from .service import event, now, redact_exception


def _step(session: Session, run: WorkflowRun, name: str) -> WorkflowStepRun:
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run.id,
            WorkflowStepRun.step_name == name,
        )
    )
    if step is None:
        raise RuntimeError(f"missing GraphRAG workflow step: {name}")
    return step


def _start_step(session: Session, run: WorkflowRun, name: str) -> None:
    step = _step(session, run, name)
    step.state, step.updated_at = "running", now()
    event(session, run, "step_started", step=name)


def _complete_step(session: Session, run: WorkflowRun, name: str, **checkpoint: object) -> None:
    step = _step(session, run, name)
    step.state, step.checkpoint_json, step.updated_at = (
        "completed",
        json.dumps({"completed": True, **checkpoint}, ensure_ascii=False),
        now(),
    )
    event(session, run, "step_completed", step=name)


def _release_lock(session: Session, run: WorkflowRun) -> None:
    lock = session.scalar(
        select(WorkspaceLock).where(
            WorkspaceLock.workflow_run_id == run.id,
            WorkspaceLock.lock_type == "graph",
        )
    )
    if lock:
        session.delete(lock)


def begin(session: Session, run_id: str):
    """Durably claim a run and snapshot DB input before external work starts."""
    run = session.get(WorkflowRun, run_id)
    if run is None or run.job_type != "graphrag_reindex" or run.state != "queued":
        return None
    held = session.scalar(
        select(WorkspaceLock).where(
            WorkspaceLock.workspace_id == run.workspace_id,
            WorkspaceLock.lock_type == "graph",
        )
    )
    if held:
        owner = session.get(WorkflowRun, held.workflow_run_id)
        if owner is None or owner.state in {"completed", "failed", "cancelled", "interrupted"}:
            # A worker can stop after it claims the GraphRAG lock. Terminal runs
            # cannot own a lock for a later reindex request.
            session.delete(held)
            session.flush()
            held = None
    if held:
        event(session, run, "blocked", lock_type="graph")
        return None
    session.add(
        WorkspaceLock(
            id=str(uuid4()),
            workspace_id=run.workspace_id,
            lock_type="graph",
            workflow_run_id=run.id,
            acquired_at=now(),
        )
    )
    run.state, run.updated_at = "running", now()
    event(session, run, "started")
    _start_step(session, run, "snapshot")
    context = WorkspaceContext.load(session, run.workspace_id)
    materializer = GraphRAGInputMaterializer(get_settings().data_path)
    update = prepare_deferred_update(
        session,
        run.workspace_id,
        context.graph_root,
        materializer,
    )
    _complete_step(session, run, "snapshot", document_count=len(update.documents))
    return update


def start_external_step(session: Session, run_id: str, name: str) -> bool:
    run = session.get(WorkflowRun, run_id)
    if run is None or run.state != "running":
        return False
    _start_step(session, run, name)
    return True


def finish_external_step(session: Session, run_id: str, name: str, **checkpoint: object) -> None:
    run = session.get(WorkflowRun, run_id)
    if run and run.state == "running":
        _complete_step(session, run, name, **checkpoint)


def complete(session: Session, run_id: str) -> None:
    run = session.get(WorkflowRun, run_id)
    if run is None or run.state != "running":
        return
    complete_deferred_update(session, run.workspace_id)
    run.state, run.finished_at, run.updated_at = "completed", now(), now()
    event(session, run, "completed")
    _release_lock(session, run)


def fail(session: Session, run_id: str, exc: Exception) -> None:
    run = session.get(WorkflowRun, run_id)
    if run is None:
        return
    details = redact_exception(exc)
    running_step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run.id,
            WorkflowStepRun.state == "running",
        )
    )
    if running_step:
        running_step.state, running_step.checkpoint_json, running_step.updated_at = (
            "failed",
            json.dumps({"error": details}, ensure_ascii=False),
            now(),
        )
    fail_deferred_update(session, run.workspace_id)
    run.state, run.finished_at, run.updated_at = "failed", now(), now()
    event(session, run, "failed", details=details)
    _release_lock(session, run)


def execute(run_id: str, run_with_lock_retry) -> bool:
    """Execute model and file operations with no SQLAlchemy transaction open."""
    update = run_with_lock_retry(lambda session: begin(session, run_id))
    if update is None:
        return False
    materializer = GraphRAGInputMaterializer(get_settings().data_path)
    adapter = GraphRAGAdapter(update.workspace_id, update.graph_root)
    try:
        run_with_lock_retry(lambda session: start_external_step(session, run_id, "materialize"))
        manifest = materializer.write(update.documents, update.workspace_id, update.graph_root)
        run_with_lock_retry(
            lambda session: finish_external_step(
                session, run_id, "materialize", document_count=len(manifest.document_version_ids)
            )
        )

        run_with_lock_retry(lambda session: start_external_step(session, run_id, "index"))
        settings_path = update.graph_root / "settings.yaml"
        adapter.config_path = settings_path if settings_path.is_file() else adapter.initialize()
        adapter.index()
        adapter.rebuild_networkx()
        def finish_index(session):
            finish_external_step(session, run_id, "index")
            active = get_settings()
            stages = [
                ("entity_extraction", "graphrag_extraction"),
                ("description_summarization", "graphrag_extraction"),
                ("community_report_generation", "graphrag_community"),
            ]
            if active.graphrag_claims_enabled:
                stages.append(("claim_extraction", "graphrag_claims"))
            for stage, layer in stages:
                record_stage_usage(
                    session,
                    update.workspace_id,
                    stage=stage,
                    provider=getattr(active, f"{layer}_provider"),
                    model=getattr(active, f"{layer}_model"),
                )

        run_with_lock_retry(finish_index)

        run_with_lock_retry(lambda session: start_external_step(session, run_id, "neo4j_sync"))
        neo4j_result = sync_graph_to_neo4j(adapter, run_id)
        run_with_lock_retry(
            lambda session: finish_external_step(
                session,
                run_id,
                "neo4j_sync",
                generation=neo4j_result.graph.generation,
                node_count=neo4j_result.graph.node_count,
                relationship_count=neo4j_result.graph.relationship_count,
                skipped_relationship_count=neo4j_result.skipped_relationship_count,
            )
        )

        run_with_lock_retry(lambda session: start_external_step(session, run_id, "mirror"))
        settings = get_settings()
        provider = (
            OllamaEmbeddingAdapter()
            if settings.embedding_provider == "ollama"
            else OpenAIEmbeddingAdapter(settings.embedding_model)
        )
        mirrored = asyncio.run(
            mirror_graph_outputs(
                adapter,
                GraphRAGQdrantAdapter(get_qdrant_client(), update.workspace_id),
                provider,
            )
        )
        run_with_lock_retry(
            lambda session: finish_external_step(session, run_id, "mirror", **mirrored)
        )
        run_with_lock_retry(lambda session: complete(session, run_id))
    except Exception as exc:
        run_with_lock_retry(lambda session, error=exc: fail(session, run_id, error))
        raise
    return True
