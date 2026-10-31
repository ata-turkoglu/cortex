import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.construction import MANDATORY_KNOWLEDGE_STAGES
from app.knowledge.extraction import (
    ExtractedEntityProperty,
    ExtractedMention,
    ExtractedSpan,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk, StageResult
from app.knowledge.production_executor import ProductionKnowledgeExecutor, _bundle_payload
from app.knowledge.provider_extractor import ProviderExtractionResult
from app.models import (
    Base,
    KnowledgeGeneration,
    KnowledgeStageState,
    WorkflowRun,
    Workspace,
    WorkspaceLock,
)
from app.workflows.knowledge import execute, prepare_stage, resume_or_begin, stage_is_running
from app.workflows.knowledge_context import checkpoint, create_context
from app.workflows.service import create_run, retry_from_failed_step


def test_context_is_idempotent_and_rejects_source_text():
    session = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(session.bind)
    now = datetime.now(UTC)
    workspace_id, generation_id, run_id = (str(uuid4()), str(uuid4()), str(uuid4()))
    session.add(
        Workspace(
            id=workspace_id, slug="context", name="Context", state="active",
            created_at=now, updated_at=now,
        )
    )
    session.add(
        KnowledgeGeneration(
            id=generation_id, workspace_id=workspace_id, source_fingerprint="source",
            state="building", failure_json=None, created_at=now, updated_at=now, activated_at=None,
        )
    )
    session.add(
        WorkflowRun(
            id=run_id,
            workspace_id=workspace_id,
            definition_id="definition",
            job_type="knowledge_reindex",
            state="queued", recovery_state=None, payload_json="{}", created_at=now, updated_at=now,
            finished_at=None,
        )
    )
    context = create_context(
        session, workspace_id=workspace_id, workflow_run_id=run_id,
        generation_id=generation_id, source_fingerprint="source",
    )
    assert create_context(
        session, workspace_id=workspace_id, workflow_run_id=run_id,
        generation_id=generation_id, source_fingerprint="source",
    ).id == context.id
    checkpoint(context, "entity_mention", {"output_fingerprint": "abc", "mention_count": 1})
    with pytest.raises(ValueError, match="source text"):
        checkpoint(context, "entity_mention", {"source_text": "must not persist"})


def test_specialized_executor_activates_only_after_every_stage_and_releases_lock():
    engine = create_engine("sqlite:///:memory:")
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    session = factory()
    now = datetime.now(UTC)
    workspace_id = str(uuid4())
    session.add(
        Workspace(
            id=workspace_id, slug="delivery", name="Delivery", state="active",
            created_at=now, updated_at=now,
        )
    )
    run = create_run(session, workspace_id, "knowledge_reindex")
    session.commit()
    run_id = run.id
    session.close()

    class Executor:
        def execute(self, stage, snapshot, generation_id):
            return StageResult(
                generation_id, snapshot.fingerprint, f"{stage}:ready", {"count": 0}
            )

    execute(run_id, factory, Executor())

    session = factory()
    completed = session.get(WorkflowRun, run_id)
    generation = session.query(KnowledgeGeneration).one()
    states = session.query(KnowledgeStageState).filter_by(generation_id=generation.id).all()
    assert completed.state == "completed"
    assert generation.state == "active"
    assert {item.stage for item in states} == set(MANDATORY_KNOWLEDGE_STAGES)
    assert all(item.state == "ready" for item in states)
    assert session.query(WorkspaceLock).count() == 0


def test_specialized_executor_retries_the_same_candidate_generation():
    engine = create_engine("sqlite:///:memory:")
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    session = factory()
    timestamp = datetime.now(UTC)
    workspace_id = str(uuid4())
    session.add(
        Workspace(
            id=workspace_id, slug="retry", name="Retry", state="active",
            created_at=timestamp, updated_at=timestamp,
        )
    )
    run = create_run(session, workspace_id, "knowledge_reindex")
    session.commit()
    run_id = run.id
    session.close()

    class FailingExecutor:
        def execute(self, stage, snapshot, generation_id):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        execute(run_id, factory, FailingExecutor())
    session = factory()
    failed_generation_id = session.query(KnowledgeGeneration).one().id
    retry_from_failed_step(session, session.get(WorkflowRun, run_id))
    session.commit()
    session.close()

    class ReadyExecutor:
        def execute(self, stage, snapshot, generation_id):
            return StageResult(generation_id, snapshot.fingerprint, f"{stage}:ready", {})

    execute(run_id, factory, ReadyExecutor())
    session = factory()
    assert session.get(WorkflowRun, run_id).state == "completed"
    assert session.query(KnowledgeGeneration).one().id == failed_generation_id
    assert session.query(KnowledgeGeneration).one().state == "active"


def test_delayed_dispatch_cannot_reenter_a_running_knowledge_stage():
    engine = create_engine("sqlite:///:memory:")
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    session = factory()
    timestamp = datetime.now(UTC)
    workspace_id = str(uuid4())
    session.add(
        Workspace(
            id=workspace_id,
            slug="single-owner",
            name="Single owner",
            state="active",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    run = create_run(session, workspace_id, "knowledge_reindex")
    run_id = run.id
    session.commit()

    assert resume_or_begin(session, run_id)
    session.commit()
    prepare_stage(session, run_id, "entity_mention")
    session.commit()
    session.close()

    fallback_session = factory()
    assert resume_or_begin(fallback_session, run_id) is None
    assert stage_is_running(fallback_session, run_id, "entity_mention")
    assert fallback_session.get(WorkflowRun, run_id).state == "running"


def test_cached_cross_mention_property_is_quarantined_before_validation(tmp_path):
    content = "Lutfi Hasan Merter"
    snapshot = CorpusSnapshot(
        "workspace",
        "fingerprint",
        (SourceChunk("chunk", "document", "version", "logical", 0, content, "hash"),),
    )
    bundle = KnowledgeExtractionBundle(
        ExtractionMetadata("run", "provider", "model", "prompt", "schema"),
        mentions=(
            ExtractedMention("m1", "person", ExtractedSpan("chunk", 0, 5, "Lutfi", 1)),
            ExtractedMention(
                "m2", "person", ExtractedSpan("chunk", 6, 18, "Hasan Merter", 1)
            ),
        ),
        entity_properties=(
            ExtractedEntityProperty(
                "m1", "surname", "Merter", ExtractedSpan("chunk", 12, 18, "Merter", 1)
            ),
        ),
    )
    executor = object.__new__(ProductionKnowledgeExecutor)
    executor.workspace_id = "workspace"
    executor.settings = object()
    executor.extractor = object()
    executor.root = tmp_path / "knowledge-candidates"
    executor.data_root = tmp_path
    executor._retrieval = {}
    executor._artifact("generation", "extraction").write_text(
        json.dumps({"bundles": [_bundle_payload(bundle)]}), encoding="utf-8"
    )

    result = executor.entity_mentions(snapshot, "generation")

    assert result.metrics["rejected_assertion_count"] == 1
    assert result.metrics["entity_property_candidate_count"] == 0


def test_entity_mentions_extracts_all_uncached_chunks_in_one_bounded_provider_run(tmp_path):
    chunks = tuple(
        SourceChunk(f"chunk-{index}", "document", "version", "logical", index, "text", "hash")
        for index in range(3)
    )
    snapshot = CorpusSnapshot("workspace", "fingerprint", chunks)

    class RecordingExtractor:
        concurrency = 2

        def __init__(self):
            self.snapshots = []

        def extract(self, supplied_snapshot, generation_id):
            self.snapshots.append(supplied_snapshot)
            return ProviderExtractionResult(
                tuple(
                    KnowledgeExtractionBundle(
                        ExtractionMetadata("run", "provider", "model", "prompt", "schema")
                    )
                    for _ in supplied_snapshot.chunks
                ),
                evidence_count=0,
            )

    extractor = RecordingExtractor()
    executor = object.__new__(ProductionKnowledgeExecutor)
    executor.workspace_id = "workspace"
    executor.settings = object()
    executor.extractor = extractor
    executor.root = tmp_path / "knowledge-candidates"
    executor.data_root = tmp_path
    executor._retrieval = {}

    result = executor.entity_mentions(snapshot, "generation")

    assert [[item.chunk_id for item in call.chunks] for call in extractor.snapshots] == [
        ["chunk-0", "chunk-1"],
        ["chunk-2"],
    ]
    assert result.metrics["bundle_count"] == 3
    assert all(
        (
            executor._generation_root("generation")
            / "extraction-chunks"
            / f"chunk-{index}.json"
        ).is_file()
        for index in range(3)
    )
