from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.knowledge.construction import (
    MANDATORY_KNOWLEDGE_STAGES,
    RETRIEVAL_REQUIRED_STAGES,
    activate_if_ready,
    active_generation,
    create_generation,
    fail_stage,
    mark_stage_ready,
)
from app.knowledge.pipeline import StageResult, run_knowledge_construction
from app.models import Base, KnowledgeStageState, Workspace


def session_with_workspaces(*workspace_ids: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    timestamp = datetime.now(UTC)
    for workspace_id in workspace_ids:
        session.add(
            Workspace(
                id=workspace_id,
                slug=f"workspace-{workspace_id}",
                name=workspace_id,
                state="active",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    session.flush()
    return session


def ready_all(session, generation):
    for stage in MANDATORY_KNOWLEDGE_STAGES:
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint=f"{stage}-output",
        )


def test_generation_activates_after_retrieval_projections_without_canonical_or_graphrag():
    session = session_with_workspaces("a")
    generation = create_generation(session, "a", "source-v1")
    for stage in RETRIEVAL_REQUIRED_STAGES[:-1]:
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint="source-v1",
            output_fingerprint=f"{stage}-output",
        )
    assert activate_if_ready(session, generation) is False
    mark_stage_ready(
        session,
        generation,
        RETRIEVAL_REQUIRED_STAGES[-1],
        input_fingerprint="source-v1",
        output_fingerprint="dense-output",
    )
    assert activate_if_ready(session, generation) is True
    assert active_generation(session, "a").id == generation.id


def test_generation_mismatch_and_conflicting_replay_are_rejected():
    session = session_with_workspaces("a")
    generation = create_generation(session, "a", "source-v1")
    with pytest.raises(ValueError, match="does not match"):
        mark_stage_ready(
            session,
            generation,
            "bm25",
            input_fingerprint="source-v2",
            output_fingerprint="out",
        )
    mark_stage_ready(
        session,
        generation,
        "bm25",
        input_fingerprint="source-v1",
        output_fingerprint="out-a",
    )
    with pytest.raises(ValueError, match="conflicting replay"):
        mark_stage_ready(
            session,
            generation,
            "bm25",
            input_fingerprint="source-v1",
            output_fingerprint="out-b",
        )


def test_failed_candidate_preserves_previous_active_generation():
    session = session_with_workspaces("a")
    previous = create_generation(session, "a", "source-v1")
    ready_all(session, previous)
    assert activate_if_ready(session, previous)
    candidate = create_generation(session, "a", "source-v2")
    fail_stage(session, candidate, "canonical_graph", summary="adapter failed")
    assert activate_if_ready(session, candidate) is False
    assert active_generation(session, "a").id == previous.id
    assert candidate.state == "failed"


def test_activation_is_workspace_isolated():
    session = session_with_workspaces("a", "b")
    first = create_generation(session, "a", "a-v1")
    second = create_generation(session, "b", "b-v1")
    ready_all(session, first)
    ready_all(session, second)
    assert activate_if_ready(session, first)
    assert active_generation(session, "b") is None
    assert activate_if_ready(session, second)
    assert active_generation(session, "a").id == first.id
    assert active_generation(session, "b").id == second.id
    assert not session.scalars(
        select(KnowledgeStageState).where(
            KnowledgeStageState.generation_id == first.id,
            KnowledgeStageState.workspace_id == "b",
        )
    ).all()


def test_new_generation_uses_an_opaque_id():
    session = session_with_workspaces("a")
    generation = create_generation(session, "a", "same-source")
    UUID(generation.id)
    assert "same-source" not in generation.id


class RecordingExecutor:
    def __init__(self, fail_at=None, mismatch_at=None):
        self.calls = []
        self.fail_at = fail_at
        self.mismatch_at = mismatch_at
        self.user_curated = {"entity-1": "curated name"}

    def execute(self, stage, snapshot, generation_id):
        self.calls.append((stage, snapshot.workspace_id, generation_id))
        if stage == self.fail_at:
            raise RuntimeError("projection failed")
        return StageResult(
            generation_id="other-generation" if stage == self.mismatch_at else generation_id,
            input_fingerprint=snapshot.fingerprint,
            output_fingerprint=f"{stage}-output",
            metrics={"count": len(snapshot.chunks)},
        )


def test_pipeline_executes_all_projections_and_preserves_curated_state():
    session = session_with_workspaces("a")
    session_factory = sessionmaker(bind=session.bind)
    session.close()
    executor = RecordingExecutor()
    generation_id = run_knowledge_construction(session_factory, "a", executor)
    assert [item[0] for item in executor.calls] == list(MANDATORY_KNOWLEDGE_STAGES)
    assert executor.user_curated == {"entity-1": "curated name"}
    check = session_factory()
    assert active_generation(check, "a").id == generation_id
    check.close()


def test_pipeline_marks_a_mismatched_optional_result_unavailable_and_activates_retrieval():
    session = session_with_workspaces("a")
    session_factory = sessionmaker(bind=session.bind)
    session.close()
    generation_id = run_knowledge_construction(
        session_factory,
        "a",
        RecordingExecutor(mismatch_at="identity_resolution"),
    )
    check = session_factory()
    failed = check.scalar(
        select(KnowledgeStageState).where(
            KnowledgeStageState.workspace_id == "a",
            KnowledgeStageState.stage == "identity_resolution",
        )
    )
    assert failed.state == "unavailable"
    assert active_generation(check, "a").id == generation_id
    check.close()
