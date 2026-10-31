import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.knowledge.construction import (
    MANDATORY_KNOWLEDGE_STAGES,
    activate_if_ready,
    create_generation,
    mark_stage_ready,
)
from app.models import Base, QueryCutoverAttempt, QueryRuntimeActivation, Workspace
from app.query.cutover import (
    CutoverEvaluation,
    CutoverPreflight,
    active_runtime,
    attempt_cutover,
)


def _session(*workspace_ids: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    timestamp = datetime.now(UTC)
    for workspace_id in workspace_ids:
        session.add(
            Workspace(
                id=workspace_id,
                slug=workspace_id,
                name=workspace_id,
                state="active",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    session.flush()
    return session


def _active_generation(session, workspace_id: str, fingerprint: str):
    generation = create_generation(session, workspace_id, fingerprint)
    for stage in MANDATORY_KNOWLEDGE_STAGES:
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint=fingerprint,
            output_fingerprint=f"{stage}-output",
            metrics={"embedding_config_hash": "embedding"} if stage == "dense_qdrant" else None,
        )
    assert activate_if_ready(session, generation)
    return generation


@pytest.fixture(autouse=True)
def valid_generation_artifacts(monkeypatch):
    """Keep cutover unit tests focused on durable readiness and activation policy."""
    monkeypatch.setattr("app.query.cutover.load_generation_manifest", lambda *_args: ())
    monkeypatch.setattr(
        "app.query.cutover.WorkspaceBM25Index.load_generation", lambda *_args: object()
    )


def _preflight(fingerprint: str, **changes):
    values = {
        "schema_ready": True,
        "config_ready": True,
        "neo4j_ready": True,
        "runtime_ready": True,
        "current_source_fingerprint": fingerprint,
        "curation_before_fingerprint": "curation-1",
        "curation_after_fingerprint": "curation-1",
    }
    values.update(changes)
    return CutoverPreflight(**values)


def _evaluation(**changes):
    values = {
        "suite_version": "phase13-v1",
        "total_cases": 10,
        "passed_cases": 10,
        "score": 1.0,
        "minimum_score": 0.9,
    }
    values.update(changes)
    return CutoverEvaluation(**values)


def test_sharp_cutover_activates_one_exact_ready_generation():
    session = _session("workspace-a")
    generation = _active_generation(session, "workspace-a", "source-a")

    report = attempt_cutover(
        session,
        "workspace-a",
        generation.id,
        preflight=_preflight("source-a"),
        evaluation=_evaluation(),
    )

    assert report.state == "activated"
    assert report.runtime_before == "v1"
    assert report.runtime_after == "v2"
    active = active_runtime(session, "workspace-a")
    assert active.generation_id == generation.id
    assert active.evaluation_fingerprint == report.evaluation_fingerprint


def test_failed_rebuild_or_evaluation_never_changes_live_runtime():
    session = _session("workspace-a")
    previous = _active_generation(session, "workspace-a", "source-a")
    session.add(
        QueryRuntimeActivation(
            workspace_id="workspace-a",
            runtime_version="v1",
            generation_id=previous.id,
            source_fingerprint="source-a",
            evaluation_fingerprint=None,
            curation_fingerprint="curation-1",
            activated_at=None,
            updated_at=datetime.now(UTC),
        )
    )
    candidate = create_generation(session, "workspace-a", "source-b")
    report = attempt_cutover(
        session,
        "workspace-a",
        candidate.id,
        preflight=_preflight("source-b", neo4j_ready=False),
        evaluation=_evaluation(score=0.5, passed_cases=5),
    )

    assert report.state == "rejected"
    assert active_runtime(session, "workspace-a").runtime_version == "v1"
    assert active_runtime(session, "workspace-a").generation_id == previous.id
    attempt = session.scalar(select(QueryCutoverAttempt))
    assert attempt.state == "rejected"
    failures = json.loads(attempt.report_json)["failures"]
    assert "retrieval projections are not ready for one exact generation" in failures
    assert "Neo4j is not ready" not in failures
    assert "acceptance evaluation did not pass" in failures


def test_corpus_drift_and_curation_loss_fail_closed():
    session = _session("workspace-a")
    generation = _active_generation(session, "workspace-a", "source-a")

    report = attempt_cutover(
        session,
        "workspace-a",
        generation.id,
        preflight=_preflight(
            "source-b",
            curation_after_fingerprint="curation-lost",
        ),
        evaluation=_evaluation(),
    )

    assert report.state == "rejected"
    assert active_runtime(session, "workspace-a") is None
    assert "active corpus changed after the generation snapshot" in report.failures
    assert "user-curated knowledge changed during rebuild" in report.failures


def test_cutover_does_not_require_neo4j_when_retrieval_is_ready():
    session = _session("workspace-a")
    generation = _active_generation(session, "workspace-a", "source-a")

    report = attempt_cutover(
        session,
        "workspace-a",
        generation.id,
        preflight=_preflight("source-a", neo4j_ready=False),
        evaluation=_evaluation(),
    )

    assert report.state == "activated"
    assert "Neo4j is not ready" not in report.failures


def test_cutover_is_workspace_isolated():
    session = _session("workspace-a", "workspace-b")
    generation_a = _active_generation(session, "workspace-a", "source-a")
    _active_generation(session, "workspace-b", "source-b")

    attempt_cutover(
        session,
        "workspace-a",
        generation_a.id,
        preflight=_preflight("source-a"),
        evaluation=_evaluation(),
    )

    assert active_runtime(session, "workspace-a").runtime_version == "v2"
    assert active_runtime(session, "workspace-b") is None


def test_missing_candidate_is_rejected_and_audited_without_runtime_mutation():
    session = _session("workspace-a")

    report = attempt_cutover(
        session,
        "workspace-a",
        "missing-generation",
        preflight=_preflight("source-a"),
        evaluation=_evaluation(),
    )

    assert report.state == "rejected"
    assert report.failures == (
        "candidate generation is missing or outside the workspace",
    )
    assert active_runtime(session, "workspace-a") is None
    assert session.scalar(select(QueryCutoverAttempt)).generation_id == "missing-generation"
