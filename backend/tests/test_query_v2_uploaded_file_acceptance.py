import asyncio
import hashlib
import importlib.util
import json

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_session as get_chat_session
from app.api.workspaces import get_session
from app.core.config import Settings
from app.evaluation.production import PRODUCTION_SUITE_VERSION
from app.knowledge.pipeline import StageResult
from app.knowledge.production_executor import ProductionKnowledgeExecutor
from app.knowledge.source_manifest import load_generation_manifest
from app.knowledge.workflow_executor import KnowledgeWorkflowExecutor
from app.main import app
from app.models import Base, KnowledgeGeneration, Message, QueryRun
from app.providers.base import GeneratedText
from app.providers.embeddings import EmbeddingConfiguration
from app.query.answer_synthesis import AnswerSynthesizer
from app.query.conversation_service import create_conversation
from app.query.cutover import CutoverEvaluation, CutoverPreflight, attempt_cutover
from app.query.production import V2QueryServiceFactory
from app.query.understanding import SemanticTarget, SemanticUnderstanding
from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from app.retrieval.sparse import WorkspaceBM25Index
from app.workflows.knowledge import execute as execute_knowledge_reindex
from app.workflows.service import create_run


class DeterministicStructuredProvider:
    async def generate_structured(self, model, instructions, input_text, **schema):
        understanding = SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="document", description="uploaded evidence"),),
            operators=("describe", "retrieve_evidence"),
            coverage="relevant_evidence",
            confidence=1.0,
        )
        return GeneratedText(text=understanding.model_dump_json(), request_id="uploaded-fixture")


class DeterministicEmbeddingProvider:
    async def embed(self, texts):
        return [[-1.0, 0.0] if "NO-SUPPORT-991" in text else [1.0, 0.0] for text in texts]


def _foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")


def _production_retrieval_executor(settings, workspace_id):
    production = ProductionKnowledgeExecutor.__new__(ProductionKnowledgeExecutor)
    production.workspace_id = workspace_id
    production.settings = settings
    production.embedding_configuration = EmbeddingConfiguration(
        "ollama", "acceptance-embedding"
    )
    production.embedding_provider = DeterministicEmbeddingProvider()
    production.extractor = None
    production.data_root = settings.data_path.resolve()
    production.root = (
        production.data_root / "workspaces" / workspace_id / "knowledge-candidates"
    ).resolve()
    production._retrieval = {}

    def no_op(stage):
        def execute(snapshot, generation_id):
            material = f"{stage}:{generation_id}:{snapshot.fingerprint}"
            return StageResult(
                generation_id,
                snapshot.fingerprint,
                hashlib.sha256(material.encode()).hexdigest(),
                {"accepted_fixture_stage": stage},
            )

        return execute

    handlers = {
        "source_relational": production.source_relational,
        "entity_mention": no_op("entity_mention"),
        "identity_resolution": no_op("identity_resolution"),
        "relation": no_op("relation"),
        "event": no_op("event"),
        "temporal": no_op("temporal"),
        "claim_fact": no_op("claim_fact"),
        "canonical_graph": no_op("canonical_graph"),
        "bm25": lambda snapshot, generation: production.retrieval(snapshot, generation)[0],
        "dense_qdrant": lambda snapshot, generation: production.retrieval(snapshot, generation)[1],
        "graphrag": no_op("graphrag"),
    }
    return KnowledgeWorkflowExecutor(handlers)


def test_real_uploaded_file_reaches_grounded_v2_and_stays_generation_isolated(
    tmp_path, monkeypatch
):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _foreign_keys)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    settings = Settings(
        data_path=tmp_path,
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    qdrant = QdrantClient(":memory:")
    monkeypatch.setattr("app.api.uploads.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.workspaces.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.workers.broker.dispatch_workflow", lambda *_: None)
    monkeypatch.setattr("app.knowledge.production_executor.get_qdrant_client", lambda: qdrant)

    def session_override():
        session = session_local()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_session] = session_override
    try:
        client = TestClient(app)
        workspace = client.post(
            "/api/v1/workspaces", json={"name": "Uploaded V2", "slug": "uploaded-v2"}
        ).json()
        upload = client.post(
            f"/api/v1/workspaces/{workspace['id']}/uploads",
            files={
                "files": (
                    "accepted-source.txt",
                    (
                        b"The cobalt orchard archive proves the river allotment. "
                        b"Rare lexical marker zephyr-741 belongs to the validated deed."
                    ),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        uploaded = upload.json()["uploads"][0]
        assert uploaded["chunk_count"] > 0
        assert uploaded["logical_document_count"] == 1
    finally:
        app.dependency_overrides.clear()

    session = session_local()
    run = create_run(session, workspace["id"], "knowledge_reindex")
    run_id = run.id
    session.commit()
    session.close()
    execute_knowledge_reindex(
        run_id,
        session_local,
        _production_retrieval_executor(settings, workspace["id"]),
    )

    session = session_local()
    generation = session.query(KnowledgeGeneration).filter_by(state="active").one()
    generation_id = generation.id
    generation_manifest_uri = generation.source_manifest_uri
    assert generation_manifest_uri
    assert generation.source_manifest_hash
    assert generation.source_chunk_count == uploaded["chunk_count"]
    conversation = create_conversation(session, workspace["id"], "Uploaded acceptance")
    conversation_id = conversation.id
    session.commit()
    factory = V2QueryServiceFactory(
        settings=settings,
        qdrant_client=qdrant,
        planner_providers={"openai": DeterministicStructuredProvider()},
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    cutover = attempt_cutover(
        session,
        workspace["id"],
        generation_id,
        preflight=CutoverPreflight(
            schema_ready=True,
            config_ready=True,
            neo4j_ready=False,
            runtime_ready=True,
            current_source_fingerprint=generation.source_fingerprint,
            curation_before_fingerprint="uploaded-fixture-curation",
            curation_after_fingerprint="uploaded-fixture-curation",
        ),
        evaluation=CutoverEvaluation(
            suite_version=PRODUCTION_SUITE_VERSION,
            total_cases=1,
            passed_cases=1,
            score=1.0,
            minimum_score=1.0,
        ),
    )
    assert cutover.state == "activated"
    session.commit()
    inputs = factory.context_loader.load(session, workspace["id"], conversation.id)
    session.commit()
    readiness = {(item.engine, item.capability): item for item in inputs.readiness.capabilities}
    assert readiness[("retrieval", "retrieval.hybrid_search")].state == "ready"
    assert all(
        item.state == "unavailable"
        for item in inputs.readiness.capabilities
        if item.capability.startswith(("structured.", "graph."))
    )
    service = factory.build(inputs)

    grounded = asyncio.run(
        service.execute_inputs(session, "Describe the deed with zephyr-741 evidence", inputs)
    )
    repeated = asyncio.run(
        service.execute_inputs(session, "Describe the deed with zephyr-741 evidence", inputs)
    )
    assert grounded.answer.state == "grounded", {
        "logical_ir": grounded.prepared.logical_ir.model_dump(mode="json"),
        "physical_plan": grounded.prepared.physical_plan.model_dump(mode="json"),
        "package_issues": grounded.package.issues,
    }
    assert grounded.answer.citations
    assert grounded.trace.dense_result_count > 0
    assert grounded.trace.sparse_result_count > 0
    assert grounded.trace.fused_result_count > 0
    assert repeated.answer.citations == grounded.answer.citations
    assert "zephyr-741" in grounded.answer.content

    class GroundedAnswerProvider:
        async def generate_structured(self, model, instructions, input_text, **_schema):
            evidence = json.loads(input_text)["evidence"]
            match = next(item for item in evidence if "zephyr-741" in item["text"])
            return GeneratedText(
                json.dumps(
                    {
                        "insufficient": False,
                        "sentences": [
                            {
                                "text": "Doğrulanmış tapu kaydı zephyr-741 işaretini taşıyor.",
                                "evidence_ids": [match["evidence_id"]],
                            }
                        ],
                    }
                ),
                input_tokens=50,
                output_tokens=10,
            )

    factory.answer_synthesizer = AnswerSynthesizer(
        GroundedAnswerProvider(),
        provider_name="openai",
        model="gpt-5.6-luna",
        style="balanced",
        evidence_limit=10,
    )
    synthesized = asyncio.run(
        factory.build(inputs).execute_inputs(
            session, "Describe the deed with zephyr-741 evidence", inputs
        )
    )
    factory.answer_synthesizer = None
    assert synthesized.answer.metadata["answer_synthesis"] == "synthesized"
    assert synthesized.answer.state == "grounded"
    assert synthesized.answer.content.endswith("[1]")
    assert [item["chunk_id"] for item in synthesized.answer.citations] == [
        next(
            item.chunk_id
            for item in synthesized.package.citations
            if "zephyr-741" in item.source_text
        )
    ]

    sources = {
        item.chunk_id: item
        for item in load_generation_manifest(session, workspace["id"], generation_id, tmp_path)
    }
    manifest_records = {
        item["chunk_id"]: item
        for item in (
            json.loads(line)
            for line in (tmp_path / generation.source_manifest_uri).read_text().splitlines()
        )
    }
    for citation in grounded.package.citations:
        source = sources[citation.chunk_id]
        assert grounded.package.workspace_id == source.workspace_id == workspace["id"]
        assert grounded.package.generation_id == source.generation_id == generation_id
        assert citation.document_id == source.document_id
        assert citation.document_version_id == source.document_version_id
        assert citation.logical_document_id == source.logical_document_id
        assert citation.source_text == source.content
        assert (
            hashlib.sha256(citation.source_text.encode()).hexdigest()
            == manifest_records[citation.chunk_id]["content_hash"]
        )

    scope = inputs.generation_scope
    WorkspaceQdrantStore(
        qdrant,
        workspace["id"],
        embedding_config_hash=scope.embedding_config_hash,
        projection_key="other-generation",
    ).upsert(
        "chunks",
        [VectorRecord("other", [1.0, 0.0], {"content": "other generation"})],
        2,
    )
    WorkspaceQdrantStore(
        qdrant,
        "foreign-workspace",
        embedding_config_hash=scope.embedding_config_hash,
        projection_key=generation_id,
    ).upsert(
        "chunks",
        [VectorRecord("foreign", [1.0, 0.0], {"content": "foreign workspace"})],
        2,
    )
    isolated = asyncio.run(service.execute_inputs(session, "Describe zephyr-741", inputs))
    assert isolated.trace.generation_id == generation_id
    assert {item["chunk_id"] for item in isolated.answer.citations}.issubset(sources)

    unsupported = asyncio.run(service.execute_inputs(session, "NO-SUPPORT-991", inputs))
    assert unsupported.answer.state == "unsupported"
    assert unsupported.answer.citations == ()
    assert unsupported.trace.dense_result_count == 0
    assert unsupported.trace.sparse_result_count == 0
    session.close()

    # The V1 chat orchestration and workspace hybrid runtime were removed; keep it that way.
    for retired in ("app.chat", "app.aggregation", "app.retrieval.runtime"):
        assert importlib.util.find_spec(retired) is None, retired
    legacy_calls = {"workspace_dense": 0, "legacy_bm25": 0}

    def forbidden_workspace_dense(*args, **kwargs):
        legacy_calls["workspace_dense"] += 1
        raise AssertionError("workspace-only dense search is reachable")

    original_bm25_load = WorkspaceBM25Index.load

    def guarded_bm25_load(workspace_id, storage_path):
        if "knowledge-candidates" not in storage_path.parts:
            legacy_calls["legacy_bm25"] += 1
            raise AssertionError("legacy workspace BM25 is reachable")
        return original_bm25_load(workspace_id, storage_path)

    monkeypatch.setattr(
        "app.retrieval.qdrant.WorkspaceQdrantStore.search", forbidden_workspace_dense
    )
    monkeypatch.setattr(WorkspaceBM25Index, "load", staticmethod(guarded_bm25_load))

    monkeypatch.setattr(
        "app.query.production_chat.build_production_embedder",
        lambda _session: (
            EmbeddingConfiguration("ollama", "acceptance-embedding"),
            DeterministicEmbeddingProvider(),
        ),
    )
    monkeypatch.setattr(
        "app.query.production_chat.V2QueryServiceFactory", lambda **_kwargs: factory
    )
    monkeypatch.setattr(
        "app.workers.broker.summarize_conversation.send", lambda *_args, **_kwargs: None
    )

    def chat_session_override():
        chat_session = session_local()
        try:
            yield chat_session
            chat_session.commit()
        finally:
            chat_session.close()

    app.dependency_overrides[get_chat_session] = chat_session_override
    try:
        client = TestClient(app)
        grounded_response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/messages",
            json={"content": "Describe zephyr-741", "mode": "automatic"},
        )
        assert grounded_response.status_code == 200, grounded_response.text
        grounded_body = grounded_response.json()
        assert grounded_body["status"] == "completed"
        assert grounded_body["citations"]
        assert grounded_body["metadata"]["runtime"] == "v2"
        production_trace = grounded_body["metadata"]["execution_trace"]
        assert production_trace["workspace_id"] == workspace["id"]
        assert production_trace["generation_id"] == generation_id
        assert production_trace["embedding_config_hash"] == scope.embedding_config_hash
        assert production_trace["dense_result_count"] > 0
        assert production_trace["sparse_result_count"] > 0
        assert production_trace["fused_result_count"] > 0
        assert production_trace["validated_result_count"] > 0
        assert production_trace["reasoning_package_generation"] == generation_id
        assert production_trace["answer_status"] == "grounded"
        assert production_trace["citation_count"] == len(grounded_body["citations"])

        unsupported_response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/messages",
            json={"content": "NO-SUPPORT-991", "mode": "automatic"},
        )
        assert unsupported_response.status_code == 200, unsupported_response.text
        unsupported_body = unsupported_response.json()
        assert unsupported_body["metadata"]["runtime"] == "v2"
        assert unsupported_body["metadata"]["answer_state"] == "unsupported"
        assert unsupported_body["citations"] == []

        manifest_path = tmp_path / generation_manifest_uri
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        tampered_response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/messages",
            json={"content": "Describe zephyr-741 after manifest tampering", "mode": "automatic"},
        )
        assert tampered_response.status_code == 200, tampered_response.text
        tampered_body = tampered_response.json()
        assert tampered_body["status"] == "failed"
        assert tampered_body["citations"] == []
        assert tampered_body["metadata"] == {
            "runtime": "v2",
            "query_run_id": tampered_body["metadata"]["query_run_id"],
            "generation_id": generation_id,
            "answer_state": "unsupported",
            "failure_type": "SourceManifestValidationError",
            "fallback_used": False,
        }
    finally:
        app.dependency_overrides.clear()

    persisted = session_local()
    assistant_messages = persisted.query(Message).filter_by(role="assistant").all()
    query_runs = persisted.query(QueryRun).all()
    assert len(assistant_messages) == 3
    assert len(query_runs) == 3
    assert all(json.loads(item.metadata_json)["runtime"] == "v2" for item in assistant_messages)
    assert {item.state for item in query_runs} == {"completed", "failed"}
    assert {item.answer_state for item in query_runs} == {"grounded", "unsupported"}
    persisted.close()
    assert legacy_calls == {"workspace_dense": 0, "legacy_bm25": 0}
