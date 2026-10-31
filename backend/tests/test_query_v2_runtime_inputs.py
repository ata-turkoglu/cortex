from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_core import CanonicalCoreStore
from app.knowledge.construction import create_generation, mark_stage_ready
from app.models import Base, Conversation, QueryRuntimeActivation, Workspace
from app.query.runtime_inputs import RuntimeInputError, V2RuntimeContextLoader


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace",
            slug="workspace",
            name="Workspace",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Conversation(
            id="conversation",
            workspace_id="workspace",
            title="Conversation",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()
    return session


def _activate_v2(session, generation):
    session.add(
        QueryRuntimeActivation(
            workspace_id=generation.workspace_id,
            runtime_version="v2",
            generation_id=generation.id,
            source_fingerprint=generation.source_fingerprint,
            evaluation_fingerprint="fixture",
            curation_fingerprint="fixture",
            activated_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.flush()


def test_runtime_loader_builds_detached_context_readiness_and_fixed_scope():
    session = _session()
    generation = create_generation(session, "workspace", "source")
    generation.source_manifest_uri = (
        "workspaces/workspace/knowledge-candidates/g/source/manifest.jsonl"
    )
    generation.source_manifest_hash = "a" * 64
    generation.source_chunk_count = 1
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint="source",
            output_fingerprint=stage,
            metrics={"embedding_config_hash": "embedding"},
        )
    generation.state = "active"
    _activate_v2(session, generation)

    inputs = V2RuntimeContextLoader(history_limit=5).load(session, "workspace", "conversation")

    assert inputs.conversation_context.workspace_id == "workspace"
    assert inputs.generation_scope.generation_id == generation.id
    assert inputs.generation_scope_resolver.resolve("workspace") == inputs.generation_scope
    assert inputs.readiness.active_generation_id == generation.id
    readiness = {(item.engine, item.capability): item for item in inputs.readiness.capabilities}
    assert readiness[("structured", "structured.enumerate")].state == "unavailable"
    assert readiness[("structured", "structured.filter")].state == "unavailable"
    assert readiness[("retrieval", "retrieval.hybrid_search")].state == "ready"
    assert readiness[("graphrag", "graphrag.local")].state == "unavailable"


def test_runtime_loader_rejects_manifestless_active_generation():
    session = _session()
    generation = create_generation(session, "workspace", "source")
    generation.state = "active"
    _activate_v2(session, generation)
    with pytest.raises(RuntimeInputError, match="not eligible"):
        V2RuntimeContextLoader(history_limit=5).load(session, "workspace", "conversation")


def test_runtime_loader_advertises_structured_capabilities_only_from_sqlite_completeness():
    session = _session()
    generation = create_generation(session, "workspace", "source")
    generation.source_manifest_uri = "workspaces/workspace/manifest.jsonl"
    generation.source_manifest_hash = "a" * 64
    generation.source_chunk_count = 1
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint="source",
            output_fingerprint=stage,
            metrics={"embedding_config_hash": "embedding"},
        )
    mark_stage_ready(
        session,
        generation,
        "canonical_graph",
        input_fingerprint="source",
        output_fingerprint="canonical",
        metrics={"resolved_entity_property_count": 1, "entity_property_schema_version": "1"},
    )
    generation.state = "active"
    _activate_v2(session, generation)

    inputs = V2RuntimeContextLoader(history_limit=5).load(session, "workspace", "conversation")

    readiness = {(item.engine, item.capability): item for item in inputs.readiness.capabilities}
    # The legacy Neo4j projection stage does not make exhaustive SQLite reads ready.
    assert readiness[("structured", "structured.filter")].state == "unavailable"
    assert readiness[("knowledge_graph", "graph.event_population")].state == "unavailable"

    store = CanonicalCoreStore(session, "workspace")
    store.record_chunk(generation.id, "chunk", "b" * 64)
    status = store.record_status(
        generation_id=generation.id,
        manifest_hash=generation.source_manifest_hash,
        manifest_chunk_count=1,
    )
    assert status.status == "READY"
    session.commit()

    inputs = V2RuntimeContextLoader(history_limit=5).load(session, "workspace", "conversation")
    readiness = {(item.engine, item.capability): item for item in inputs.readiness.capabilities}
    assert readiness[("structured", "structured.filter")].state == "ready"
    assert readiness[("knowledge_graph", "graph.event_population")].state == "unavailable"
    assert readiness[("knowledge_graph", "graph.event_filter")].state == "unavailable"


def test_runtime_loader_keeps_structured_queryability_for_a_partial_canonical_generation():
    session = _session()
    generation = create_generation(session, "workspace", "source")
    generation.source_manifest_uri = "workspaces/workspace/manifest.jsonl"
    generation.source_manifest_hash = "c" * 64
    generation.source_chunk_count = 1
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint="source",
            output_fingerprint=stage,
            metrics={"embedding_config_hash": "embedding"},
        )
    generation.state = "active"
    _activate_v2(session, generation)
    store = CanonicalCoreStore(session, "workspace")
    store.record_chunk(generation.id, "chunk", "d" * 64)
    mention = store.persist_person_mention(
        generation_id=generation.id,
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk",
        span_start=0,
        span_end=4,
        source_text="A.B.",
        extractor_version="test",
    )
    assert store.decide_person(mention).decision == "UNRESOLVED"
    status = store.record_status(
        generation_id=generation.id,
        manifest_hash=generation.source_manifest_hash,
        manifest_chunk_count=1,
    )
    assert status.status == "PARTIAL"

    inputs = V2RuntimeContextLoader(history_limit=5).load(session, "workspace", "conversation")
    readiness = {(item.engine, item.capability): item for item in inputs.readiness.capabilities}

    assert readiness[("structured", "structured.enumerate")].state == "ready"
    assert readiness[("structured", "structured.filter")].state == "ready"
