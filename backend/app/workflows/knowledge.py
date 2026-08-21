"""Durable claim boundary for the specialized knowledge_reindex worker."""

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..knowledge.construction import (
    MANDATORY_KNOWLEDGE_STAGES,
    activate_if_ready,
    create_generation,
    fail_stage,
    mark_stage_ready,
    mark_stage_running,
)
from ..knowledge.pipeline import CorpusSnapshot, StageResult, snapshot_active_corpus
from ..models import (
    KnowledgeGeneration,
    KnowledgeReindexRunContext,
    KnowledgeStageState,
    WorkflowRun,
    WorkflowStepRun,
    WorkspaceLock,
)
from .knowledge_context import checkpoint, create_context
from .service import event, now


def begin(session: Session, run_id: str):
    """Claim once and persist generation/context before external model or store work."""
    run = session.get(WorkflowRun, run_id)
    if not run or run.job_type != "knowledge_reindex" or run.state != "queued":
        return None
    held = session.scalar(
        select(WorkspaceLock).where(
            WorkspaceLock.workspace_id == run.workspace_id, WorkspaceLock.lock_type == "index"
        )
    )
    if held:
        owner = session.get(WorkflowRun, held.workflow_run_id)
        if owner is None or owner.state in {
            "completed", "failed", "cancelled", "interrupted"
        }:
            session.delete(held)
            session.flush()
            held = None
    if held:
        event(session, run, "blocked", lock_type="index")
        return None
    session.add(
        WorkspaceLock(
            id=str(uuid4()), workspace_id=run.workspace_id, lock_type="index",
            workflow_run_id=run.id, acquired_at=now(),
        )
    )
    snapshot = snapshot_active_corpus(session, run.workspace_id)
    generation = create_generation(session, run.workspace_id, snapshot.fingerprint)
    create_context(
        session, workspace_id=run.workspace_id, workflow_run_id=run.id,
        generation_id=generation.id, source_fingerprint=snapshot.fingerprint,
    )
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run.id,
            WorkflowStepRun.step_name == "source_relational",
        )
    )
    if step is None:
        raise RuntimeError("knowledge_reindex source_relational step is missing")
    mark_stage_ready(
        session, generation, "source_relational", input_fingerprint=snapshot.fingerprint,
        output_fingerprint=snapshot.fingerprint, metrics={"chunk_count": len(snapshot.chunks)},
    )
    step.state, step.checkpoint_json, step.updated_at = (
        "completed",
        json.dumps({"generation_id": generation.id}),
        now(),
    )
    run.state, run.updated_at = "running", now()
    event(session, run, "started", generation_id=generation.id)
    event(session, run, "step_completed", step="source_relational")
    return generation.id


def resume_or_begin(session: Session, run_id: str) -> str | None:
    """Claim a queued run or resume its immutable candidate after worker retry."""
    run = session.get(WorkflowRun, run_id)
    if run and run.job_type == "knowledge_reindex" and run.state in {"queued", "running"}:
        context = (
            session.query(KnowledgeReindexRunContext)
            .filter_by(workflow_run_id=run_id, workspace_id=run.workspace_id)
            .one_or_none()
        )
        if context is None and run.state == "running":
            raise RuntimeError("running knowledge_reindex has no durable context")
        if context is None:
            return begin(session, run_id)
        snapshot = snapshot_active_corpus(session, run.workspace_id)
        if snapshot.fingerprint != context.source_fingerprint:
            raise RuntimeError("active corpus changed before knowledge_reindex retry")
        generation = session.get(KnowledgeGeneration, context.generation_id)
        if generation is None:
            raise RuntimeError("knowledge_reindex retry candidate is missing")
        if generation.state == "failed":
            generation.state = "building"
            generation.failure_json = None
            generation.updated_at = now()
            for state in session.scalars(
                select(KnowledgeStageState).where(
                    KnowledgeStageState.generation_id == generation.id,
                    KnowledgeStageState.state == "failed",
                )
            ):
                state.state, state.error_json, state.updated_at = "pending", None, now()
        lock = session.scalar(
            select(WorkspaceLock).where(
                WorkspaceLock.workflow_run_id == run_id,
                WorkspaceLock.workspace_id == run.workspace_id,
                WorkspaceLock.lock_type == "index",
            )
        )
        if lock is None:
            session.add(
                WorkspaceLock(
                    id=str(uuid4()), workspace_id=run.workspace_id, lock_type="index",
                    workflow_run_id=run.id, acquired_at=now(),
                )
            )
        if run.state == "queued":
            run.state, run.updated_at = "running", now()
            event(session, run, "resumed", generation_id=context.generation_id)
        return context.generation_id
    return begin(session, run_id)


def fail(session: Session, run_id: str, stage: str, summary: str) -> None:
    """Fail a candidate safely; never alter the currently active generation."""
    run = session.get(WorkflowRun, run_id)
    if not run:
        return
    context = (
        session.query(KnowledgeReindexRunContext).filter_by(workflow_run_id=run_id).one_or_none()
    )
    if context:
        generation = session.get(KnowledgeGeneration, context.generation_id)
        if generation and generation.state == "building":
            fail_stage(session, generation, stage, summary=summary)
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run_id, WorkflowStepRun.step_name == stage
        )
    )
    if step and step.state != "completed":
        step.state, step.checkpoint_json, step.updated_at = (
            "failed",
            json.dumps({"summary": summary[:500]}),
            now(),
        )
    run.state, run.finished_at, run.updated_at = "failed", now(), now()
    event(session, run, "failed", details={"summary": summary[:500]})
    lock = session.scalar(
        select(WorkspaceLock).where(
            WorkspaceLock.workflow_run_id == run_id, WorkspaceLock.lock_type == "index"
        )
    )
    if lock:
        session.delete(lock)


def prepare_stage(session: Session, run_id: str, stage: str) -> tuple[CorpusSnapshot, str]:
    run = session.get(WorkflowRun, run_id)
    context = session.query(KnowledgeReindexRunContext).filter_by(workflow_run_id=run_id).one()
    if not run or run.state != "running":
        raise RuntimeError("knowledge_reindex run is not running")
    snapshot = snapshot_active_corpus(session, run.workspace_id)
    if snapshot.fingerprint != context.source_fingerprint:
        raise RuntimeError("active corpus changed after claim")
    generation = session.get(KnowledgeGeneration, context.generation_id)
    mark_stage_running(session, generation, stage, input_fingerprint=snapshot.fingerprint)
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run_id, WorkflowStepRun.step_name == stage
        )
    )
    step.state, step.updated_at = "running", now()
    event(session, run, "step_started", step=stage)
    return snapshot, generation.id


def complete_stage(session: Session, run_id: str, stage: str, result: StageResult) -> None:
    run = session.get(WorkflowRun, run_id)
    context = session.query(KnowledgeReindexRunContext).filter_by(workflow_run_id=run_id).one()
    if (
        result.generation_id != context.generation_id
        or result.input_fingerprint != context.source_fingerprint
    ):
        raise ValueError("stage result does not match candidate generation")
    generation = session.get(KnowledgeGeneration, context.generation_id)
    mark_stage_ready(
        session, generation, stage, input_fingerprint=context.source_fingerprint,
        output_fingerprint=result.output_fingerprint, metrics=result.metrics,
    )
    checkpoint(
        context,
        stage,
        {"output_fingerprint": result.output_fingerprint, "metrics": result.metrics},
    )
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run_id, WorkflowStepRun.step_name == stage
        )
    )
    step.state, step.checkpoint_json, step.updated_at = (
        "completed",
        json.dumps({"output_fingerprint": result.output_fingerprint}),
        now(),
    )
    event(session, run, "step_completed", step=stage)


def stage_is_complete(session: Session, run_id: str, stage: str) -> bool:
    step = session.scalar(
        select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == run_id,
            WorkflowStepRun.step_name == stage,
        )
    )
    return bool(step and step.state == "completed")


def complete(session: Session, run_id: str) -> None:
    """Atomically activate a fully ready candidate and release its workflow lock."""
    run = session.get(WorkflowRun, run_id)
    if not run or run.state != "running":
        return
    context = (
        session.query(KnowledgeReindexRunContext).filter_by(workflow_run_id=run_id).one()
    )
    generation = session.get(KnowledgeGeneration, context.generation_id)
    if generation is None or not activate_if_ready(session, generation):
        raise RuntimeError("knowledge candidate is not ready for activation")
    run.state, run.finished_at, run.updated_at = "completed", now(), now()
    event(session, run, "completed", generation_id=generation.id)
    lock = session.scalar(
        select(WorkspaceLock).where(
            WorkspaceLock.workflow_run_id == run_id, WorkspaceLock.lock_type == "index"
        )
    )
    if lock:
        session.delete(lock)


def execute(run_id: str, session_factory, executor) -> None:
    """Run each external adapter between short durable SQLite transactions."""
    session = session_factory()
    try:
        generation_id = resume_or_begin(session, run_id)
        session.commit()
    finally:
        session.close()
    if not generation_id:
        return
    for stage in MANDATORY_KNOWLEDGE_STAGES[1:]:
        session = session_factory()
        try:
            if stage_is_complete(session, run_id, stage):
                continue
            snapshot, generation_id = prepare_stage(session, run_id, stage)
            session.commit()
        finally:
            session.close()
        try:
            result = executor.execute(stage, snapshot, generation_id)
        except Exception as exc:
            session = session_factory()
            try:
                fail(session, run_id, stage, str(exc))
                session.commit()
            finally:
                session.close()
            raise
        session = session_factory()
        try:
            complete_stage(session, run_id, stage, result)
            session.commit()
        finally:
            session.close()
    session = session_factory()
    try:
        complete(session, run_id)
        session.commit()
    finally:
        session.close()
