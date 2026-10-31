"""Durable, generation-consistent readiness gate for knowledge construction."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KnowledgeGeneration, KnowledgeStageState

MANDATORY_KNOWLEDGE_STAGES = (
    "source_relational",
    "entity_mention",
    "identity_resolution",
    "relation",
    "event",
    "temporal",
    "claim_fact",
    "canonical_graph",
    "bm25",
    "dense_qdrant",
    "graphrag",
)

# A candidate becomes the V2 retrieval generation when its immutable source
# authority and both retrieval projections agree.  Canonical and GraphRAG
# stages remain durable checkpoints, but they enable capability families rather
# than making grounded retrieval unavailable.
RETRIEVAL_REQUIRED_STAGES = ("source_relational", "bm25", "dense_qdrant")
OPTIONAL_CAPABILITY_STAGES = tuple(
    stage for stage in MANDATORY_KNOWLEDGE_STAGES if stage not in RETRIEVAL_REQUIRED_STAGES
)


def _now() -> datetime:
    return datetime.now(UTC)


def create_generation(
    session: Session, workspace_id: str, source_fingerprint: str
) -> KnowledgeGeneration:
    """Create an isolated candidate; the currently active generation is untouched."""
    timestamp = _now()
    generation = KnowledgeGeneration(
        id=str(uuid4()),
        workspace_id=workspace_id,
        source_fingerprint=source_fingerprint,
        state="building",
        failure_json=None,
        created_at=timestamp,
        updated_at=timestamp,
        activated_at=None,
    )
    session.add(generation)
    session.flush()
    session.add_all(
        KnowledgeStageState(
            id=str(uuid4()),
            workspace_id=workspace_id,
            generation_id=generation.id,
            stage=stage,
            state="pending",
            input_fingerprint=None,
            output_fingerprint=None,
            metrics_json=None,
            error_json=None,
            updated_at=timestamp,
        )
        for stage in MANDATORY_KNOWLEDGE_STAGES
    )
    # Production sessions deliberately disable autoflush. Readiness lookups in
    # the same short transaction must still see all newly created checkpoints.
    session.flush()
    return generation


def stage_state(
    session: Session, generation: KnowledgeGeneration, stage: str
) -> KnowledgeStageState:
    if stage not in MANDATORY_KNOWLEDGE_STAGES:
        raise ValueError(f"unknown mandatory knowledge stage: {stage}")
    state = session.scalar(
        select(KnowledgeStageState).where(
            KnowledgeStageState.generation_id == generation.id,
            KnowledgeStageState.workspace_id == generation.workspace_id,
            KnowledgeStageState.stage == stage,
        )
    )
    if state is None:
        raise ValueError("generation stage is missing or outside the workspace")
    return state


def mark_stage_running(
    session: Session,
    generation: KnowledgeGeneration,
    stage: str,
    *,
    input_fingerprint: str,
) -> KnowledgeStageState:
    if generation.state != "building" and not (
        generation.state == "active" and stage in OPTIONAL_CAPABILITY_STAGES
    ):
        raise ValueError("only a building generation accepts this stage update")
    state = stage_state(session, generation, stage)
    state.state = "running"
    state.input_fingerprint = input_fingerprint
    state.error_json = None
    state.updated_at = generation.updated_at = _now()
    return state


def mark_stage_ready(
    session: Session,
    generation: KnowledgeGeneration,
    stage: str,
    *,
    input_fingerprint: str,
    output_fingerprint: str,
    metrics: dict[str, object] | None = None,
) -> KnowledgeStageState:
    if input_fingerprint != generation.source_fingerprint:
        raise ValueError("stage input does not match the candidate generation")
    state = stage_state(session, generation, stage)
    if state.state == "ready":
        if (
            state.input_fingerprint != input_fingerprint
            or state.output_fingerprint != output_fingerprint
        ):
            raise ValueError("conflicting replay for completed generation stage")
        return state
    if generation.state != "building" and not (
        generation.state == "active" and stage in OPTIONAL_CAPABILITY_STAGES
    ):
        raise ValueError("only a building generation accepts this stage update")
    state.state = "ready"
    state.input_fingerprint = input_fingerprint
    state.output_fingerprint = output_fingerprint
    state.metrics_json = json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True)
    state.error_json = None
    state.updated_at = generation.updated_at = _now()
    return state


def fail_stage(
    session: Session,
    generation: KnowledgeGeneration,
    stage: str,
    *,
    summary: str,
) -> KnowledgeStageState:
    state = stage_state(session, generation, stage)
    error = {"summary": summary[:500]}
    state.state = "failed"
    state.error_json = json.dumps(error, ensure_ascii=False)
    state.updated_at = _now()
    generation.state = "failed"
    generation.failure_json = state.error_json
    generation.updated_at = state.updated_at
    return state


def mark_stage_unavailable(
    session: Session,
    generation: KnowledgeGeneration,
    stage: str,
    *,
    summary: str,
) -> KnowledgeStageState:
    """Record an unavailable optional capability without failing retrieval activation."""
    if stage not in OPTIONAL_CAPABILITY_STAGES:
        raise ValueError("only optional capability stages may be unavailable")
    if generation.state != "building":
        raise ValueError("only a building generation accepts stage updates")
    state = stage_state(session, generation, stage)
    state.state = "unavailable"
    state.error_json = json.dumps({"summary": summary[:500]}, ensure_ascii=False)
    state.updated_at = generation.updated_at = _now()
    return state


def validate_manifest_projection_agreement(
    session: Session, generation: KnowledgeGeneration, data_root: Path
) -> bool:
    """Fail closed unless the persisted candidate projections match its manifest."""
    from .source_manifest import SourceManifestValidationError, load_generation_manifest

    try:
        sources = load_generation_manifest(
            session, generation.workspace_id, generation.id, data_root
        )
    except SourceManifestValidationError:
        return False
    expected_ids = sorted(source.chunk_id for source in sources)
    expected_hashes = {
        source.chunk_id: hashlib.sha256(source.content.encode("utf-8")).hexdigest()
        for source in sources
    }
    states = {
        state.stage: state
        for state in session.scalars(
            select(KnowledgeStageState).where(
                KnowledgeStageState.generation_id == generation.id,
                KnowledgeStageState.workspace_id == generation.workspace_id,
            )
        )
    }
    for stage in ("bm25", "dense_qdrant"):
        state = states.get(stage)
        try:
            metrics = json.loads(state.metrics_json or "{}") if state else {}
        except json.JSONDecodeError:
            return False
        if (
            metrics.get("chunk_count") != generation.source_chunk_count
            or metrics.get("source_manifest_hash") != generation.source_manifest_hash
            or metrics.get("chunk_ids") != expected_ids
            or metrics.get("content_hashes") != expected_hashes
        ):
            return False
    return True


def activate_if_ready(session: Session, generation: KnowledgeGeneration) -> bool:
    """Atomically replace the active generation only after a consistent full gate."""
    if generation.state == "active":
        return True
    if generation.state != "building":
        return False
    states = session.scalars(
        select(KnowledgeStageState).where(
            KnowledgeStageState.generation_id == generation.id,
            KnowledgeStageState.workspace_id == generation.workspace_id,
        )
    ).all()
    by_stage = {state.stage: state for state in states}
    ready = all(
        stage in by_stage
        and by_stage[stage].state == "ready"
        and by_stage[stage].input_fingerprint == generation.source_fingerprint
        and bool(by_stage[stage].output_fingerprint)
        for stage in RETRIEVAL_REQUIRED_STAGES
    )
    if not ready:
        return False
    timestamp = _now()
    previous = session.scalars(
        select(KnowledgeGeneration).where(
            KnowledgeGeneration.workspace_id == generation.workspace_id,
            KnowledgeGeneration.state == "active",
            KnowledgeGeneration.id != generation.id,
        )
    ).all()
    for item in previous:
        item.state = "superseded"
        item.updated_at = timestamp
    generation.state = "active"
    generation.activated_at = timestamp
    generation.updated_at = timestamp
    return True


def active_generation(session: Session, workspace_id: str) -> KnowledgeGeneration | None:
    return session.scalar(
        select(KnowledgeGeneration).where(
            KnowledgeGeneration.workspace_id == workspace_id,
            KnowledgeGeneration.state == "active",
        )
    )
