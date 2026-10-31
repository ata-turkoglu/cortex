import asyncio
import hashlib
import json
from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.knowledge.canonical_core import CanonicalCoreStore
from app.knowledge.construction import create_generation, mark_stage_ready
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.source_manifest import write_generation_manifest
from app.models import Base, Conversation, Message, QueryRun, QueryRuntimeActivation, Workspace
from app.providers.base import GeneratedText
from app.providers.embeddings import EmbeddingConfiguration
from app.query.answer import AnswerEngine
from app.query.context import ContextRevisionConflict
from app.query.execution import V2DenseAdapter, V2PlanExecutor, V2SparseAdapter
from app.query.production import V2QueryServiceFactory
from app.query.runtime import QueryV2PreparationService
from app.query.scope import GenerationScope
from app.query.source_runtime import ConfiguredV2QueryEmbedder
from app.query.understanding import (
    SemanticRelationAggregate,
    SemanticTarget,
    SemanticTypedFilter,
    SemanticUnderstanding,
)
from app.query.understanding.planner import SemanticPlannerAdapter
from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from app.retrieval.schemas import Evidence
from app.retrieval.sparse import GenerationBM25Store, SparseDocument, WorkspaceBM25Index


class DeterministicStructuredProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, model, instructions, input_text, **schema):
        self.calls += 1
        understanding = SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="document", description="workspace evidence"),),
            operators=("describe", "retrieve_evidence"),
            coverage="relevant_evidence",
            confidence=1.0,
        )
        return GeneratedText(text=understanding.model_dump_json(), request_id="deterministic")


class DeterministicEmbeddingProvider:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class ExhaustivePeopleProvider:
    async def generate_structured(self, model, instructions, input_text, **schema):
        understanding = SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="entity", description="people"),),
            typed_filters=(
                SemanticTypedFilter(
                    target_type="person", property="surname", operator="eq", value="Merter"
                ),
            ),
            structured_operation="rank",
            relation_aggregate=SemanticRelationAggregate(
                source_type="person",
                relation="owns",
                target_type="asset_property",
                direction="descending",
            ),
            coverage="corpus_required",
            confidence=1.0,
        )
        return GeneratedText(text=understanding.model_dump_json(), request_id="exhaustive-fixture")


def _settings(tmp_path):
    return Settings(
        data_path=tmp_path,
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )


def _session(*workspace_ids):
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    for workspace_id in workspace_ids:
        session.add(
            Workspace(
                id=workspace_id,
                slug=workspace_id,
                name=workspace_id,
                state="active",
                created_at=now,
                updated_at=now,
            )
        )
    session.add(
        Conversation(
            id="conversation",
            workspace_id=workspace_ids[0],
            title="Acceptance",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()
    return session


def _candidate(session, tmp_path, client, workspace_id="workspace", contents=None):
    contents = ["The archive records the blue orchard deed."] if contents is None else contents
    generation = create_generation(session, workspace_id, "source-fingerprint")
    chunks = tuple(
        SourceChunk(
            f"chunk-{index}",
            f"document-{index}",
            f"version-{index}",
            f"logical-{index}",
            index,
            content,
            hashlib.sha256(content.encode()).hexdigest(),
        )
        for index, content in enumerate(contents)
    )
    snapshot = CorpusSnapshot(workspace_id, "source-fingerprint", chunks)
    identity = write_generation_manifest(tmp_path, snapshot, generation.id)
    generation.source_manifest_uri = identity.uri
    generation.source_manifest_hash = identity.sha256
    generation.source_chunk_count = identity.chunk_count
    configuration = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2)
    evidence = [
        Evidence(
            workspace_id,
            "knowledge_candidate",
            chunk.content,
            0.0,
            chunk.document_id,
            chunk.document_version_id,
            chunk.chunk_id,
            f"passage {chunk.ordinal + 1}",
            {
                "knowledge_generation_id": generation.id,
                "logical_document_id": chunk.logical_document_id,
                "content_hash": chunk.content_hash,
            },
        )
        for chunk in chunks
    ]
    bm25_path = (
        tmp_path / "workspaces" / workspace_id / "knowledge-candidates" / generation.id / "bm25"
    )
    WorkspaceBM25Index(
        workspace_id,
        [SparseDocument(item.chunk_id or "", item.content, item) for item in evidence],
        bm25_path,
        generation_id=generation.id,
    ).save()
    dense_store = WorkspaceQdrantStore(
        client,
        workspace_id,
        embedding_config_hash=configuration.fingerprint,
        projection_key=generation.id,
    )
    if chunks:
        dense_store.upsert(
            "chunks",
            [
                VectorRecord(
                    chunk.chunk_id,
                    [1.0, float(index) / 10],
                    {
                        "content": chunk.content,
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "document_version_id": chunk.document_version_id,
                        "logical_document_id": chunk.logical_document_id,
                        "content_hash": chunk.content_hash,
                        "citation_label": f"passage {chunk.ordinal + 1}",
                    },
                )
                for index, chunk in enumerate(chunks)
            ],
            2,
        )
    else:
        dense_store.ensure_collection("chunks", 2)
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint="source-fingerprint",
            output_fingerprint=stage,
            metrics={"embedding_config_hash": configuration.fingerprint},
        )
    generation.state = "active"
    session.flush()
    return generation, configuration


def _activate(session, generation):
    session.merge(
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


def _factory(tmp_path, client, provider):
    return V2QueryServiceFactory(
        settings=_settings(tmp_path),
        qdrant_client=client,
        planner_providers={"openai": provider},
        embedding_provider=DeterministicEmbeddingProvider(),
    )


def test_factory_query_embedder_rejects_generation_fingerprint_mismatch(tmp_path):
    factory = _factory(tmp_path, QdrantClient(":memory:"), DeterministicStructuredProvider())

    with pytest.raises(ValueError, match="GENERATION_EMBEDDING_FINGERPRINT_MISMATCH"):
        asyncio.run(
            factory.query_embedder.embed(
                "query", GenerationScope("workspace", "generation", "wrong-fingerprint")
            )
        )


def test_factory_constructs_only_generation_bound_production_components(tmp_path):
    session = _session("workspace")
    client = QdrantClient(":memory:")
    generation, _ = _candidate(session, tmp_path, client)
    _activate(session, generation)
    provider = DeterministicStructuredProvider()
    factory = _factory(tmp_path, client, provider)
    inputs = factory.context_loader.load(session, "workspace", "conversation")

    service = factory.build(inputs)

    assert isinstance(factory.planner, SemanticPlannerAdapter)
    assert isinstance(service.preparation, QueryV2PreparationService)
    assert isinstance(service.query_embedder, ConfiguredV2QueryEmbedder)
    assert isinstance(service.executor, V2PlanExecutor)
    assert isinstance(service.executor.dense, V2DenseAdapter)
    assert isinstance(service.executor.dense.store, WorkspaceQdrantStore)
    assert service.executor.dense.store.projection_key == inputs.generation_scope.generation_id
    assert isinstance(service.executor.sparse, V2SparseAdapter)
    assert isinstance(service.executor.sparse.store, GenerationBM25Store)
    assert isinstance(service.answer_engine, AnswerEngine)


def test_persisted_state_reaches_real_v2_pipeline_with_dense_sparse_fusion(tmp_path):
    session = _session("workspace", "foreign")
    client = QdrantClient(":memory:")
    generation, _ = _candidate(
        session,
        tmp_path,
        client,
        contents=[
            "The archive records the blue orchard deed.",
            "Lexical token zephyr-741 appears in the cadastral note.",
        ],
    )
    _activate(session, generation)
    provider = DeterministicStructuredProvider()
    factory = _factory(tmp_path, client, provider)
    inputs = factory.context_loader.load(session, "workspace", "conversation")
    session.commit()

    service = factory.build(inputs)
    result = asyncio.run(
        service.execute_inputs(session, "Describe the zephyr-741 archive evidence", inputs)
    )
    repeated = asyncio.run(
        service.execute_inputs(session, "Describe the zephyr-741 archive evidence", inputs)
    )

    assert provider.calls == 2
    assert result.prepared.logical_ir.state == "resolved"
    assert result.prepared.physical_plan.state == "ready"
    assert result.trace.workspace_id == "workspace"
    assert result.trace.generation_id == generation.id
    assert result.trace.dense_result_count > 0
    assert result.trace.sparse_result_count > 0
    assert result.trace.fused_result_count == 2
    assert result.trace.validated_result_count == 2
    assert result.answer.state == "grounded"
    assert result.answer.citations
    assert repeated.answer.citations == result.answer.citations
    assert all(item["chunk_id"].startswith("chunk-") for item in result.answer.citations)
    assert result.package.generation_id == generation.id


def test_empty_generation_is_unsupported_without_citations(tmp_path):
    session = _session("workspace")
    client = QdrantClient(":memory:")
    generation, _ = _candidate(session, tmp_path, client, contents=[])
    _activate(session, generation)
    provider = DeterministicStructuredProvider()
    factory = _factory(tmp_path, client, provider)
    inputs = factory.context_loader.load(session, "workspace", "conversation")
    session.commit()

    result = asyncio.run(factory.build(inputs).execute_inputs(session, "Nothing here", inputs))

    assert result.trace.dense_result_count == 0
    assert result.trace.sparse_result_count == 0
    assert result.answer.state == "unsupported"
    assert result.answer.citations == ()


def test_loaded_pointer_snapshot_and_qdrant_filters_isolate_execution(tmp_path):
    session = _session("workspace", "foreign")
    client = QdrantClient(":memory:")
    generation, configuration = _candidate(session, tmp_path, client)
    _activate(session, generation)
    factory = _factory(tmp_path, client, DeterministicStructuredProvider())
    inputs = factory.context_loader.load(session, "workspace", "conversation")
    other, _ = _candidate(session, tmp_path, client)
    activation = session.get(QueryRuntimeActivation, "workspace")
    activation.runtime_version = "v1"
    activation.generation_id = other.id
    activation.source_fingerprint = "other"
    foreign = WorkspaceQdrantStore(
        client,
        "foreign",
        embedding_config_hash=configuration.fingerprint,
        projection_key=generation.id,
    )
    foreign.upsert(
        "chunks",
        [VectorRecord("foreign", [1.0, 0.0], {"content": "foreign"})],
        2,
    )
    session.commit()

    result = asyncio.run(factory.build(inputs).execute_inputs(session, "Describe it", inputs))

    assert result.trace.generation_id == generation.id
    assert result.package.generation_id == generation.id
    assert {citation["chunk_id"] for citation in result.answer.citations} == {"chunk-0"}


def test_factory_registers_generation_bound_multi_engine_dispatch(tmp_path):
    session = _session("workspace")
    client = QdrantClient(":memory:")
    generation, _ = _candidate(session, tmp_path, client)
    _activate(session, generation)
    factory = _factory(tmp_path, client, DeterministicStructuredProvider())
    inputs = factory.context_loader.load(session, "workspace", "conversation")

    service = factory.build(inputs)

    for engine in ("retrieval", "structured", "knowledge_graph", "graphrag"):
        assert service.executor.registry.engine_for(engine)


@pytest.mark.parametrize("context_conflict", [False, True])
def test_exhaustive_sqlite_v2_path_retains_zeroes_and_uses_no_fallbacks(
    tmp_path, monkeypatch, context_conflict
):
    """Production V2 path: SQLite canonical authority works without Neo4j or retrieval.

    A concurrent context revision must not discard the already validated answer.
    """
    session = _session("workspace")
    client = QdrantClient(":memory:")
    contents = [
        "Ali Merter owns Istanbul Kadikoy Moda 303 ada 16 parsel.",
        "Ali Merter owns Istanbul Kadikoy Moda 303 ada 17 parsel.",
        "Ayse Merter owns Istanbul Kadikoy Moda 303 ada 18 parsel.",
        "Zeynep Merter is named in the archive.",
    ]
    generation, configuration = _candidate(session, tmp_path, client, contents=contents)
    store = CanonicalCoreStore(session, "workspace")
    people = []
    for ordinal, (name, content) in enumerate(
        zip(
            ("Ali Merter", "Ali Merter", "Ayse Merter", "Zeynep Merter"),
            contents,
            strict=True,
        )
    ):
        person = store.persist_person_mention(
            generation_id=generation.id,
            document_id=f"document-{ordinal}",
            document_version_id=f"version-{ordinal}",
            logical_document_id=f"logical-{ordinal}",
            chunk_id=f"chunk-{ordinal}",
            span_start=content.index(name),
            span_end=content.index(name) + len(name),
            source_text=name,
            extractor_version="acceptance",
        )
        store.decide_person(
            person,
            candidate_ids=(store.decide_person(people[0]).canonical_entity_id,)
            if ordinal == 1
            else (),
            candidate_provenance=(
                "prior accepted canonical Person in this production fixture"
                if ordinal == 1
                else None
            ),
        )
        people.append(person)
        store.record_chunk(
            generation.id,
            f"chunk-{ordinal}",
            hashlib.sha256(content.encode()).hexdigest(),
        )
    for ordinal, parcel in enumerate(("16", "17", "18")):
        content = contents[ordinal]
        property_text = f"Istanbul Kadikoy Moda 303 ada {parcel} parsel"
        property_mention = store.persist_property_mention(
            generation_id=generation.id,
            document_id=f"document-{ordinal}",
            document_version_id=f"version-{ordinal}",
            logical_document_id=f"logical-{ordinal}",
            chunk_id=f"chunk-{ordinal}",
            span_start=content.index(property_text),
            span_end=content.index(property_text) + len(property_text),
            source_text=property_text,
            extractor_version="acceptance",
        )
        property_record = store.upsert_property(
            {
                "province": "Istanbul",
                "district": "Kadikoy",
                "neighborhood": "Moda",
                "ada": "303",
                "parsel": parcel,
            }
        )
        assert property_record is not None
        store.persist_ownership_assertion(
            generation_id=generation.id,
            person_mention=people[ordinal],
            property_mention=property_mention,
            property_record=property_record,
            span_start=0,
            span_end=len(content),
            source_text=content,
            assertion_rule_version="acceptance",
        )
    assert store.record_status(
        generation_id=generation.id,
        manifest_hash=generation.source_manifest_hash,
        manifest_chunk_count=4,
    ).status == "READY"
    _activate(session, generation)
    session.commit()

    from app.knowledge.graph import Neo4jConfigurationError

    monkeypatch.setattr(
        "app.query.production.Neo4jGraphAdapter.from_settings",
        staticmethod(lambda _workspace_id: (_ for _ in ()).throw(Neo4jConfigurationError("off"))),
    )
    factory = V2QueryServiceFactory(
        settings=_settings(tmp_path),
        qdrant_client=client,
        planner_providers={"openai": ExhaustivePeopleProvider()},
        embedding_provider=DeterministicEmbeddingProvider(),
        embedding_configuration=configuration,
        canonical_session=session,
    )
    from app.query.production_chat import execute_v2_chat

    if context_conflict:

        def conflicting_save(*_args, **_kwargs):
            raise ContextRevisionConflict("context revision changed")

        monkeypatch.setattr("app.query.production_chat.save_conversation_context", conflicting_save)
    _, assistant, run = asyncio.run(
        execute_v2_chat(
            session,
            "workspace",
            "conversation",
            (
                "Merter soyadlı kişileri listele, her biri için belgelerde geçen taşınmaz "
                "sayısını belirt ve en fazla taşınmaz kaydı olan kişiden en aza doğru sırala."
            ),
            "automatic",
            factory=factory,
        )
    )

    metadata = json.loads(assistant.metadata_json)
    assert assistant.status == run.state == "completed"
    assert metadata["answer_state"] == "corpus_complete", {
        "issues": metadata["issues"],
        "logical_ir": metadata["logical_ir"],
        "query_plan": metadata["query_plan"],
    }
    assert "1. Ali Merter — 2 taşınmaz kaydı" in assistant.content
    assert "2. Ayse Merter — 1 taşınmaz kaydı" in assistant.content
    assert "3. Zeynep Merter — 0 taşınmaz kaydı" in assistant.content
    plan_steps = metadata["query_plan"]["graph"]["steps"]
    assert [step["engine"] for step in plan_steps] == [
        "structured",
        "structured",
        "structured",
        "result_evidence",
    ]
    assert {step["capability"] for step in plan_steps[:-1]} == {
        "structured.enumerate",
        "structured.filter",
        "structured.relation_aggregate",
    }
    assert any(
        node["kind"] == "scan" and node["resource"] == "person"
        for node in metadata["logical_ir"]["nodes"]
    )
    assert metadata["execution_trace"]["dense_result_count"] == 0
    assert metadata["execution_trace"]["sparse_result_count"] == 0
    assert metadata["execution_trace"]["fused_result_count"] == 0
    assert session.get(Message, assistant.id) is not None
    assert session.get(QueryRun, run.id) is not None
