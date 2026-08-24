"""Opt-in acceptance test for the real Neo4j GraphRAG persistence boundary."""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.engines.structured import StructuredQueryEngine, load_canonical_population
from app.graphrag.adapter import GraphRAGAdapter
from app.graphrag.neo4j import Neo4jBackedGraphRAGAdapter
from app.knowledge import KnowledgeAuthority, new_canonical_id
from app.knowledge.claims import ClaimStage, KnowledgeClaim, link_contradiction
from app.knowledge.construction import create_generation, mark_stage_ready
from app.knowledge.entities import (
    CanonicalEntity,
    CanonicalEntityProperty,
    EntityAlias,
    EntityMention,
    EntityPropertyValueType,
    EntityType,
    IdentityDecisionKind,
)
from app.knowledge.events import CanonicalEvent
from app.knowledge.extraction import (
    ExtractedEntityProperty,
    ExtractedMention,
    ExtractedSpan,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)
from app.knowledge.graph import GraphNode, Neo4jGraphAdapter
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.production_executor import ProductionKnowledgeExecutor, _bundle_payload
from app.knowledge.provenance import ExactSourceProvenance
from app.knowledge.relations import CanonicalRelation, RelationSupport
from app.knowledge.source_manifest import write_generation_manifest
from app.knowledge.temporal import TemporalExpression, TemporalPrecision
from app.models import Base, Conversation, QueryRuntimeActivation, Workspace
from app.providers.base import GeneratedText
from app.providers.embeddings import EmbeddingConfiguration
from app.query.ir import FieldReference, FilterNode, IRValidationError, ScanNode
from app.query.planning import ExecutionStep, FailurePolicy, PlanTrace, ReadinessRequirement
from app.query.production import V2QueryServiceFactory
from app.query.production_chat import execute_v2_chat
from app.query.understanding import (
    SemanticEntity,
    SemanticGovernedField,
    SemanticRelation,
    SemanticTarget,
    SemanticTemporalConstraint,
    SemanticTypedFilter,
    SemanticUnderstanding,
)
from app.query.understanding.planner import SemanticPlannerOutputError
from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore

pytestmark = pytest.mark.skipif(
    os.getenv("CORTEX_NEO4J_LIVE") != "1",
    reason="set CORTEX_NEO4J_LIVE=1 to run the Neo4j acceptance test",
)


def test_live_graphrag_sync_is_workspace_isolated(tmp_path):
    settings = Settings()
    generation = f"phase-03-{uuid4()}"
    workspace_a = f"phase-03-a-{uuid4()}"
    workspace_b = f"phase-03-b-{uuid4()}"
    graph_root = tmp_path / "graphrag"
    graph_root.mkdir()
    (graph_root / "entities.json").write_text(
        json.dumps(
            [
                {"id": "ankara", "text": "Ankara", "attributes": {"title": "Ankara"}},
                {
                    "id": "turkiye",
                    "text": "Türkiye",
                    "attributes": {"title": "Türkiye"},
                },
            ]
        ),
        encoding="utf-8",
    )
    (graph_root / "relationships.json").write_text(
        json.dumps(
            [
                {
                    "id": "capital",
                    "text": "başkentidir",
                    "attributes": {"source": "Ankara", "target": "Türkiye"},
                }
            ]
        ),
        encoding="utf-8",
    )
    for resource_type in ("reports", "text_units", "documents"):
        (graph_root / f"{resource_type}.json").write_text("[]", encoding="utf-8")

    first = Neo4jGraphAdapter.from_settings(workspace_a, settings=settings)
    second = Neo4jGraphAdapter.from_settings(workspace_b, settings=settings)
    try:
        first.verify_connectivity()
        synced = Neo4jBackedGraphRAGAdapter(
            GraphRAGAdapter(workspace_a, graph_root), first
        ).sync_extracted(generation)
        second.ensure_schema()
        second.replace_extracted_generation(
            generation,
            (GraphNode("sentinel", "acceptance", generation),),
            (),
        )

        assert synced.graph.node_count == 2
        assert synced.graph.relationship_count == 1
        assert first.extracted_node_count(generation) == 2
        assert second.extracted_node_count(generation) == 1

        first.replace_extracted_generation(generation, (), ())
        assert first.extracted_node_count(generation) == 0
        assert second.extracted_node_count(generation) == 1
    finally:
        first.replace_extracted_generation(generation, (), ())
        second.replace_extracted_generation(generation, (), ())
        first.close()
        second.close()


def test_live_canonical_precedence_curation_provenance_and_conflicts():
    settings = Settings()
    workspace_id = f"phase-04-{uuid4()}"
    generation = f"phase-04-{uuid4()}"
    adapter = Neo4jGraphAdapter.from_settings(workspace_id, settings=settings)

    def source(text, version, chunk):
        return ExactSourceProvenance(
            workspace_id=workspace_id,
            document_id=f"document-{version}",
            document_version_id=version,
            logical_document_id=f"logical-{version}",
            chunk_id=chunk,
            start_offset=5,
            end_offset=5 + len(text),
            source_text=text,
            extraction_run_id="run-live",
            provider="acceptance",
            model="deterministic-fixture",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            confidence=0.95,
            validation_state="validated",
            generation=generation,
        )

    mention_a = EntityMention(
        new_canonical_id(),
        "Ayşe Yılmaz",
        EntityType.PERSON,
        source("Ayşe Yılmaz", "version-a", "chunk-a"),
    )
    mention_b = EntityMention(
        new_canonical_id(),
        "A. Yılmaz",
        EntityType.PERSON,
        source("A. Yılmaz", "version-b", "chunk-b"),
    )
    primary = CanonicalEntity.create(
        EntityType.PERSON,
        "Ayşe Yılmaz",
        KnowledgeAuthority.USER_CURATED,
        aliases=(EntityAlias(new_canonical_id(), "Ayşe Yılmaz", KnowledgeAuthority.USER_CURATED),),
        mentions=(mention_a,),
    )
    duplicate = CanonicalEntity.create(
        EntityType.PERSON,
        "A. Yılmaz",
        KnowledgeAuthority.EXTRACTED,
        mentions=(mention_b,),
    )
    try:
        adapter.ensure_schema()
        adapter.upsert_canonical_entity(primary, generation)
        adapter.upsert_canonical_entity(duplicate, generation)
        adapter.upsert_canonical_entity(
            CanonicalEntity(
                primary.entity_id,
                EntityType.PERSON,
                "lower-precedence overwrite",
                KnowledgeAuthority.EXTRACTED,
            ),
            generation,
        )
        stored = {item.entity_id: item for item in adapter.list_canonical_entities()}
        assert stored[primary.entity_id].display_name == "Ayşe Yılmaz"
        assert stored[primary.entity_id].authority == "user_curated"
        assert len(adapter.entity_evidence(primary.entity_id)) == 1

        adapter.add_alias(primary.entity_id, "Ayşe Kaya", "reviewed source evidence")
        adapter.remove_alias(primary.entity_id, "Ayşe Kaya", "alias retracted")
        adapter.merge_canonical_entities(
            primary.entity_id,
            (duplicate.entity_id,),
            evidence_ids=(mention_a.provenance.evidence_id, mention_b.provenance.evidence_id),
            reason="same person after exact-span review",
        )
        adapter.split_canonical_entity(
            primary.entity_id,
            (
                ("Ayşe Yılmaz", (mention_a.mention_id,)),
                ("Aylin Yılmaz", (mention_b.mention_id,)),
            ),
            evidence_ids=(mention_a.provenance.evidence_id, mention_b.provenance.evidence_id),
            reason="mentions refer to different people",
        )
        assert {item.kind for item in adapter.identity_history()} >= {
            "alias_add",
            "alias_remove",
            "merge",
            "split",
        }

        left = KnowledgeClaim(
            new_canonical_id(),
            primary.entity_id,
            "registered_city",
            "Ankara",
            ClaimStage.SUPPORTED,
            KnowledgeAuthority.VALIDATED,
            generation,
            (mention_a.provenance,),
        )
        right = KnowledgeClaim(
            new_canonical_id(),
            primary.entity_id,
            "registered_city",
            "İzmir",
            ClaimStage.SUPPORTED,
            KnowledgeAuthority.VALIDATED,
            generation,
            (mention_b.provenance,),
        )
        adapter.upsert_claim(left)
        adapter.upsert_claim(right)
        adapter.link_claim_conflict(link_contradiction(left, right))
    finally:
        adapter.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=adapter.database,
        )
        adapter.close()


def test_live_governed_entity_properties_are_scoped_evidenced_and_filterable():
    workspace_a, workspace_b = f"property-a-{uuid4()}", f"property-b-{uuid4()}"
    generation_a, generation_b = f"property-g1-{uuid4()}", f"property-g2-{uuid4()}"
    entity_id = new_canonical_id()

    def source(workspace_id, generation, text, suffix):
        return ExactSourceProvenance(
            workspace_id=workspace_id,
            document_id=f"document-{suffix}",
            document_version_id=f"version-{suffix}",
            logical_document_id=f"logical-{suffix}",
            chunk_id=f"chunk-{suffix}",
            start_offset=0,
            end_offset=len(text),
            source_text=text,
            extraction_run_id="property-run",
            provider="acceptance",
            model="deterministic-fixture",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            confidence=0.95,
            validation_state="validated",
            generation=generation,
        )

    def step(workspace_id, generation, capability, node_id):
        return ExecutionStep(
            step_id=f"property.{node_id}",
            engine="structured",
            capability=capability,
            output_type="entity_set",
            coverage_expectation="exhaustive",
            readiness=ReadinessRequirement(workspace_id=workspace_id, generation_id=generation),
            failure_policy=FailurePolicy(action="fail_closed"),
            trace=PlanTrace(logical_node_ids=(node_id,), selection_reason="live property fixture"),
        )

    first = Neo4jGraphAdapter.from_settings(workspace_a, settings=Settings())
    second = Neo4jGraphAdapter.from_settings(workspace_b, settings=Settings())
    try:
        for adapter in (first, second):
            adapter.ensure_schema()
        for generation, surname in ((generation_a, "Merter"), (generation_b, "Kaya")):
            mention_source = source(workspace_a, generation, "Person A", f"mention-{generation}")
            property_source = source(workspace_a, generation, surname, f"property-{generation}")
            entity = CanonicalEntity(
                entity_id,
                EntityType.PERSON,
                "Person A",
                KnowledgeAuthority.EXTRACTED,
                mentions=(
                    EntityMention(
                        new_canonical_id(), "Person A", EntityType.PERSON, mention_source
                    ),
                ),
            )
            first.upsert_canonical_entity(entity, generation)
            first.upsert_canonical_entity_property(
                CanonicalEntityProperty(
                    new_canonical_id(),
                    entity_id,
                    "surname",
                    surname,
                    EntityPropertyValueType.STRING,
                    KnowledgeAuthority.EXTRACTED,
                    generation,
                    property_source,
                )
            )
        second_entity = CanonicalEntity.create(
            EntityType.PERSON,
            "Person B",
            mentions=(
                EntityMention(
                    new_canonical_id(),
                    "Person B",
                    EntityType.PERSON,
                    source(workspace_b, generation_a, "Person B", "workspace-b-mention"),
                ),
            ),
        )
        second.upsert_canonical_entity(second_entity, generation_a)
        second.upsert_canonical_entity_property(
            CanonicalEntityProperty(
                new_canonical_id(),
                second_entity.entity_id,
                "surname",
                "Merter",
                EntityPropertyValueType.STRING,
                KnowledgeAuthority.EXTRACTED,
                generation_a,
                source(workspace_b, generation_a, "Merter", "workspace-b-property"),
            )
        )

        population = load_canonical_population(first, generation_a, "person")
        assert population.workspace_id == workspace_a
        assert [record.record_id for record in population.records] == [entity_id]
        assert population.records[0].values["surname"] == "Merter"
        assert any(item.source_text == "Merter" for item in population.records[0].evidence)
        engine = StructuredQueryEngine(workspace_a, generation_a)
        scan = ScanNode(
            node_id="people",
            workspace_id=workspace_a,
            resource="person",
            output_type="entity_set",
            population_mode="exhaustive",
        )
        scanned, _ = engine.execute(
            step(workspace_a, generation_a, "structured.enumerate", "people"),
            scan,
            population=population,
        )
        filtered, result = engine.execute(
            step(workspace_a, generation_a, "structured.filter", "surname"),
            FilterNode(
                node_id="surname",
                inputs=("people",),
                output_type="entity_set",
                field=FieldReference(resource="person", field="surname"),
                comparator="eq",
                value="Merter",
            ),
            (scanned,),
        )
        assert [record.record_id for record in filtered.records] == [entity_id]
        assert any(item.source_text == "Merter" for item in result.text_evidence)
        second_generation_population = load_canonical_population(first, generation_b, "person")
        assert second_generation_population.records[0].values["surname"] == "Kaya"
        assert first.queryable_property_vocabulary(generation_a) == {
            "person": frozenset({"surname"})
        }
    finally:
        for adapter, workspace_id in ((first, workspace_a), (second, workspace_b)):
            adapter.driver.execute_query(
                "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
                workspace_id=workspace_id,
                database_=adapter.database,
            )
            adapter.close()


def test_live_conflicting_property_candidates_are_persisted_but_withheld(tmp_path):
    workspace_id = f"property-conflict-{uuid4()}"
    generation_id, entity_id = f"property-conflict-generation-{uuid4()}", new_canonical_id()
    text = "Ali Merter Mertel"

    def span(value):
        start = text.index(value)
        return ExtractedSpan("chunk-conflict", start, start + len(value), value, 0.99)

    snapshot = CorpusSnapshot(
        workspace_id,
        "conflict-fixture",
        (
            SourceChunk(
                "chunk-conflict",
                "document-conflict",
                "version-conflict",
                "logical-conflict",
                0,
                text,
                "content-hash-conflict",
            ),
        ),
    )
    settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
    )
    executor = ProductionKnowledgeExecutor(workspace_id, settings=settings)
    bundle = KnowledgeExtractionBundle(
        ExtractionMetadata("conflict-run", "acceptance", "fixture", "prompt-v1", "schema-v1"),
        mentions=(ExtractedMention("person", "person", span("Ali")),),
        entity_properties=(
            ExtractedEntityProperty("person", "surname", "Merter", span("Merter")),
            ExtractedEntityProperty("person", "surname", "Mertel", span("Mertel")),
        ),
    )
    executor._artifact(generation_id, "extraction").write_text(
        json.dumps({"bundles": [_bundle_payload(bundle)]}), encoding="utf-8"
    )
    executor._artifact(generation_id, "identity").write_text(
        json.dumps(
            {
                "mapping": [
                    {
                        "bundle_index": 0,
                        "local_id": "person",
                        "mention_id": new_canonical_id(),
                        "entity_id": entity_id,
                        "decision": "unresolved",
                        "candidate_entity_ids": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = Neo4jGraphAdapter.from_settings(workspace_id, settings=settings)
    try:
        executor.canonical_graph(snapshot, generation_id)
        records, _, _ = adapter.driver.execute_query(
            "MATCH (p:CortexEntityProperty {workspace_id: $workspace_id, generation: $generation})"
            "-[:SUPPORTED_BY]->(e:CortexEvidence {workspace_id: $workspace_id, "
            "generation: $generation}) "
            "RETURN p.status AS status, p.value AS value, e.evidence_id AS evidence_id "
            "ORDER BY value",
            workspace_id=workspace_id,
            generation=generation_id,
            database_=adapter.database,
        )
        assert [(row["status"], row["value"]) for row in records] == [
            ("conflicted", "Mertel"),
            ("conflicted", "Merter"),
        ]
        assert all(row["evidence_id"] for row in records)
        population = load_canonical_population(adapter, generation_id, "person")
        assert population.records[0].values.get("surname") is None
        engine = StructuredQueryEngine(workspace_id, generation_id)
        scan = ScanNode(
            node_id="people",
            workspace_id=workspace_id,
            resource="person",
            output_type="entity_set",
            population_mode="exhaustive",
        )

        def step(capability, node_id):
            return ExecutionStep(
                step_id=f"conflict.{node_id}",
                engine="structured",
                capability=capability,
                output_type="entity_set",
                coverage_expectation="exhaustive",
                readiness=ReadinessRequirement(
                    workspace_id=workspace_id, generation_id=generation_id
                ),
                failure_policy=FailurePolicy(action="fail_closed"),
                trace=PlanTrace(logical_node_ids=(node_id,), selection_reason="conflict fixture"),
            )

        scanned, _ = engine.execute(
            step("structured.enumerate", "people"), scan, population=population
        )
        for value in ("Merter", "Mertel"):
            node_id = f"filter-{value.casefold()}"
            filtered, _ = engine.execute(
                step("structured.filter", node_id),
                FilterNode(
                    node_id=node_id,
                    inputs=("people",),
                    output_type="entity_set",
                    field=FieldReference(resource="person", field="surname"),
                    comparator="eq",
                    value=value,
                ),
                (scanned,),
            )
            assert filtered.records == ()
    finally:
        adapter.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=adapter.database,
        )
        adapter.close()


class _SemanticFixtureProvider:
    """Deterministic model boundary only; lowering, planning, and execution stay real."""

    async def generate_structured(self, model, instructions, input_text, **schema):
        query = json.loads(input_text)["query"]
        value = "Demir" if "Demir" in query else "Merter"
        property_name = "unknown_field" if "bilinmeyen" in query else "surname"
        operation = "count" if "kaç" in query else "list"
        understanding = SemanticUnderstanding(
            state="resolved",
            typed_filters=(
                SemanticTypedFilter(
                    target_type="person", property=property_name, operator="eq", value=value
                ),
            ),
            structured_operation=operation,
            operators=("enumerate",),
            coverage="corpus_required",
            confidence=1.0,
        )
        return GeneratedText(text=understanding.model_dump_json(), request_id="list-count-e2e")


class _EmbeddingFixtureProvider:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class _AnalyticsFixtureProvider:
    """Deterministic semantic boundary for the three governed analytics acceptances."""

    async def generate_structured(self, model, instructions, input_text, **schema):
        query = json.loads(input_text)["query"]
        group_by = SemanticGovernedField(target_type="person", property="surname")
        if "group" in query:
            understanding = SemanticUnderstanding(
                state="resolved",
                structured_operation="group",
                group_by=group_by,
                coverage="corpus_required",
                confidence=1.0,
            )
        elif "rank" in query:
            understanding = SemanticUnderstanding(
                state="resolved",
                structured_operation="rank",
                group_by=group_by,
                rank_direction="descending",
                coverage="corpus_required",
                confidence=1.0,
            )
        elif "compare" in query:
            understanding = SemanticUnderstanding(
                state="resolved",
                structured_operation="compare",
                typed_filters=(
                    SemanticTypedFilter(
                        target_type="person", property="surname", operator="eq", value="Merter"
                    ),
                    SemanticTypedFilter(
                        target_type="person", property="surname", operator="eq", value="Subasi"
                    ),
                ),
                coverage="corpus_required",
                confidence=1.0,
            )
        else:
            raise AssertionError(f"unexpected analytics fixture query: {query}")
        return GeneratedText(text=understanding.model_dump_json(), request_id="analytics-e2e")


class _RelationTraversalFixtureProvider:
    """Schema-valid direct relation semantics; production lowering/execution stay real."""

    async def generate_structured(self, model, instructions, input_text, **schema):
        query = json.loads(input_text)["query"]
        if "Onlar" in query or "onlar" in query:
            return GeneratedText(
                text=SemanticUnderstanding(
                    state="unresolved",
                    entities=(
                        SemanticEntity(
                            reference_id="previous-results",
                            mention="onlar",
                            entity_type="person",
                            reference_kind="conversation_result",
                        ),
                    ),
                    relations=(
                        SemanticRelation(
                            predicate="parent_of",
                            subject_reference_id="previous-results",
                            direction="outgoing",
                            target_entity_type="person",
                        ),
                    ),
                    operators=("resolve_reference", "traverse_relation"),
                    unresolved_questions=("Which final canonical results should be traversed?",),
                    coverage="relevant_evidence",
                    confidence=1.0,
                ).model_dump_json(),
                request_id="conversation-referent-e2e",
            )
        return GeneratedText(
            text=SemanticUnderstanding(
                state="resolved",
                entities=(
                    SemanticEntity(
                        reference_id="parent",
                        mention="Parent A",
                        entity_type="person",
                    ),
                ),
                relations=(
                    SemanticRelation(
                        predicate="parent_of",
                        subject_reference_id="parent",
                        direction="outgoing",
                        target_entity_type="person",
                    ),
                ),
                operators=("traverse_relation",),
                coverage="relevant_evidence",
                confidence=1.0,
            ).model_dump_json(),
            request_id="relation-traversal-e2e",
        )


class _ExactDateEventFixtureProvider:
    """Deterministic semantic output; the real V2 path owns all material work."""

    async def generate_structured(self, model, instructions, input_text, **schema):
        query = json.loads(input_text)["query"]
        if "31.02.1974" in query:
            # Return provider-shaped JSON so SemanticPlannerAdapter, rather than the fixture,
            # proves impossible calendar dates are rejected before execution.
            return GeneratedText(
                text=json.dumps(
                    {
                        "schema_version": "1.0",
                        "state": "resolved",
                        "targets": [{"target_type": "event", "description": "events"}],
                        "temporal_constraints": [
                            {
                                "role": "event_date",
                                "original_text": "31.02.1974",
                                "normalized_start": "1974-02-31",
                                "normalized_end": "1974-02-31",
                                "precision": "day",
                                "uncertainty": "certain",
                            }
                        ],
                        "confidence": 1.0,
                    }
                ),
                request_id="exact-date-invalid",
            )
        date_text = "14.06.1974" if "14.06.1974" in query else "12.06.1974"
        return GeneratedText(
            text=SemanticUnderstanding(
                state="resolved",
                targets=(SemanticTarget(target_type="event", description="events"),),
                temporal_constraints=(
                    SemanticTemporalConstraint(
                        role="event_date",
                        original_text=date_text,
                        precision="day",
                        uncertainty="certain",
                    ),
                ),
                confidence=1.0,
            ).model_dump_json(),
            request_id="exact-date-event",
        )


class _InvalidStructuredSemanticFixtureProvider:
    """Returns schema-valid but vocabulary-invalid structured semantics."""

    def __init__(self, target_type, property_name, value):
        self.target_type = target_type
        self.property_name = property_name
        self.value = value

    async def generate_structured(self, model, instructions, input_text, **schema):
        understanding = SemanticUnderstanding(
            state="resolved",
            typed_filters=(
                SemanticTypedFilter(
                    target_type=self.target_type,
                    property=self.property_name,
                    operator="eq",
                    value=self.value,
                ),
            ),
            structured_operation="count",
            operators=("enumerate",),
            coverage="corpus_required",
            confidence=1.0,
        )
        return GeneratedText(
            text=understanding.model_dump_json(), request_id="invalid-structured-semantics"
        )


def _live_invalid_structured_semantics_fixture(tmp_path, monkeypatch, planner_provider):
    """Create one valid person.surname generation for invalid semantic requests."""
    workspace_id = f"invalid-structured-semantics-{uuid4()}"
    graph_settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
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
    conversation_id = str(uuid4())
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Invalid structured semantics acceptance",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()
    generation = create_generation(session, workspace_id, "invalid-structured-semantics")
    text = "Ali Merter"
    chunk = SourceChunk(
        "chunk-1",
        "document-1",
        "version-1",
        "logical-1",
        0,
        text,
        hashlib.sha256(text.encode()).hexdigest(),
    )
    snapshot = CorpusSnapshot(workspace_id, generation.source_fingerprint, (chunk,))
    manifest = write_generation_manifest(tmp_path, snapshot, generation.id)
    generation.source_manifest_uri, generation.source_manifest_hash = manifest.uri, manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    fingerprint = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2).fingerprint
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint=stage,
            metrics={"embedding_config_hash": fingerprint},
        )
    mark_stage_ready(
        session,
        generation,
        "canonical_graph",
        input_fingerprint=generation.source_fingerprint,
        output_fingerprint="canonical",
        metrics={"resolved_entity_property_count": 1, "entity_property_schema_version": "1"},
    )
    generation.state = "active"
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=generation.id,
            source_fingerprint=generation.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()
    source = ExactSourceProvenance(
        workspace_id=workspace_id,
        document_id=chunk.document_id,
        document_version_id=chunk.document_version_id,
        logical_document_id=chunk.logical_document_id,
        chunk_id=chunk.chunk_id,
        start_offset=0,
        end_offset=len(text),
        source_text=text,
        extraction_run_id="invalid-structured-semantics",
        provider="fixture",
        model="fixture",
        prompt_version="v1",
        schema_version="v1",
        confidence=1.0,
        validation_state="validated",
        generation=generation.id,
    )
    surname_source = ExactSourceProvenance(
        workspace_id=workspace_id,
        document_id=chunk.document_id,
        document_version_id=chunk.document_version_id,
        logical_document_id=chunk.logical_document_id,
        chunk_id=chunk.chunk_id,
        start_offset=text.index("Merter"),
        end_offset=len(text),
        source_text="Merter",
        extraction_run_id="invalid-structured-semantics",
        provider="fixture",
        model="fixture",
        prompt_version="v1",
        schema_version="v1",
        confidence=1.0,
        validation_state="validated",
        generation=generation.id,
    )
    graph = Neo4jGraphAdapter.from_settings(workspace_id, settings=graph_settings)
    graph.ensure_schema()
    entity = CanonicalEntity.create(
        EntityType.PERSON,
        "Ali Merter",
        mentions=(EntityMention(new_canonical_id(), text, EntityType.PERSON, source),),
    )
    graph.upsert_canonical_entity(entity, generation.id)
    graph.upsert_canonical_entity_property(
        CanonicalEntityProperty(
            new_canonical_id(),
            entity.entity_id,
            "surname",
            "Merter",
            EntityPropertyValueType.STRING,
            KnowledgeAuthority.EXTRACTED,
            generation.id,
            surname_source,
        )
    )
    original_reader = Neo4jGraphAdapter.from_settings
    monkeypatch.setattr(
        "app.query.production.Neo4jGraphAdapter.from_settings",
        staticmethod(
            lambda current_workspace: original_reader(current_workspace, settings=graph_settings)
        ),
    )
    factory = V2QueryServiceFactory(
        settings=graph_settings,
        qdrant_client=QdrantClient(":memory:"),
        planner_providers={"openai": planner_provider},
        embedding_provider=_EmbeddingFixtureProvider(),
    )
    inputs = factory.context_loader.load(session, workspace_id, conversation_id)
    return session, graph, factory.build(inputs), inputs, workspace_id, generation.id


def _forbid_material_execution(*args, **kwargs):
    raise AssertionError("invalid structured semantics reached material execution")


def test_live_invalid_governed_field_fails_closed_without_retrieval_fallback(tmp_path, monkeypatch):
    fixture = _live_invalid_structured_semantics_fixture(
        tmp_path,
        monkeypatch,
        _InvalidStructuredSemanticFixtureProvider("person", "favorite_color", "blue"),
    )
    session, graph, service, inputs, workspace_id, generation_id = fixture
    try:
        assert graph.queryable_property_vocabulary(generation_id) == {
            "person": frozenset({"surname"})
        }
        assert service.property_vocabulary_loader(inputs.generation_scope) == {
            "person": frozenset({"surname"})
        }
        monkeypatch.setattr(
            "app.query.service.V2PlanExecutor.execute_plan", _forbid_material_execution
        )
        monkeypatch.setattr("app.query.execution.V2DenseAdapter.search", _forbid_material_execution)
        monkeypatch.setattr(
            "app.query.execution.V2SparseAdapter.search", _forbid_material_execution
        )
        monkeypatch.setattr("app.query.answer.AnswerEngine.render", _forbid_material_execution)
        with pytest.raises(IRValidationError) as error:
            asyncio.run(
                service.execute_inputs(session, "Mavi favori renkli kişiler kaç kişi var?", inputs)
            )
        assert str(error.value) == "field is not declared for person: favorite_color"
    finally:
        graph.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        graph.close()
        session.close()


def test_live_invalid_entity_property_combination_fails_closed(tmp_path, monkeypatch):
    fixture = _live_invalid_structured_semantics_fixture(
        tmp_path,
        monkeypatch,
        _InvalidStructuredSemanticFixtureProvider("organization", "surname", "Merter"),
    )
    session, graph, service, inputs, workspace_id, generation_id = fixture
    try:
        assert graph.queryable_property_vocabulary(generation_id) == {
            "person": frozenset({"surname"})
        }
        assert "organization" not in service.property_vocabulary_loader(inputs.generation_scope)
        monkeypatch.setattr(
            "app.query.service.V2PlanExecutor.execute_plan", _forbid_material_execution
        )
        monkeypatch.setattr("app.query.execution.V2DenseAdapter.search", _forbid_material_execution)
        monkeypatch.setattr(
            "app.query.execution.V2SparseAdapter.search", _forbid_material_execution
        )
        monkeypatch.setattr("app.query.answer.AnswerEngine.render", _forbid_material_execution)
        with pytest.raises(IRValidationError) as error:
            asyncio.run(
                service.execute_inputs(session, "Merter soyadlı kuruluşlar kaç tane?", inputs)
            )
        assert str(error.value) == "field is not declared for organization: surname"
    finally:
        graph.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        graph.close()
        session.close()


def test_live_count_is_exhaustive_and_not_retrieval_top_k_bound(tmp_path, monkeypatch):
    """COUNT uses the canonical generation population, not dense retrieval cardinality."""
    workspace_id = f"count-top-k-{uuid4()}"
    graph_settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
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
    conversation_id = str(uuid4())
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Top-k COUNT acceptance",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()

    names = ("Ali Merter", "Ayşe Merter", "Bora Merter", "Cem Merter", "Deniz Merter")
    generation = create_generation(session, workspace_id, "count-top-k-source")
    chunks = tuple(
        SourceChunk(
            f"chunk-{index}",
            f"document-{index}",
            f"version-{index}",
            f"logical-{index}",
            index,
            name,
            hashlib.sha256(name.encode()).hexdigest(),
        )
        for index, name in enumerate(names)
    )
    snapshot = CorpusSnapshot(workspace_id, generation.source_fingerprint, chunks)
    manifest = write_generation_manifest(tmp_path, snapshot, generation.id)
    generation.source_manifest_uri, generation.source_manifest_hash = manifest.uri, manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    fingerprint = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2).fingerprint
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint=stage,
            metrics={"embedding_config_hash": fingerprint},
        )
    mark_stage_ready(
        session,
        generation,
        "canonical_graph",
        input_fingerprint=generation.source_fingerprint,
        output_fingerprint="canonical",
        metrics={"resolved_entity_property_count": 5, "entity_property_schema_version": "1"},
    )
    generation.state = "active"
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=generation.id,
            source_fingerprint=generation.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()

    graph = Neo4jGraphAdapter.from_settings(workspace_id, settings=graph_settings)
    qdrant = QdrantClient(":memory:")
    try:
        graph.ensure_schema()
        for index, name in enumerate(names):
            source = ExactSourceProvenance(
                workspace_id=workspace_id,
                document_id=chunks[index].document_id,
                document_version_id=chunks[index].document_version_id,
                logical_document_id=chunks[index].logical_document_id,
                chunk_id=chunks[index].chunk_id,
                start_offset=0,
                end_offset=len(name),
                source_text=name,
                extraction_run_id="count-top-k",
                provider="fixture",
                model="fixture",
                prompt_version="v1",
                schema_version="v1",
                confidence=1.0,
                validation_state="validated",
                generation=generation.id,
            )
            entity = CanonicalEntity.create(
                EntityType.PERSON,
                name,
                mentions=(EntityMention(new_canonical_id(), name, EntityType.PERSON, source),),
            )
            graph.upsert_canonical_entity(entity, generation.id)
            graph.upsert_canonical_entity_property(
                CanonicalEntityProperty(
                    new_canonical_id(),
                    entity.entity_id,
                    "surname",
                    "Merter",
                    EntityPropertyValueType.STRING,
                    KnowledgeAuthority.EXTRACTED,
                    generation.id,
                    source,
                )
            )

        dense_store = WorkspaceQdrantStore(
            qdrant,
            workspace_id,
            embedding_config_hash=fingerprint,
            projection_key=generation.id,
        )
        dense_store.upsert(
            "chunks",
            (
                VectorRecord(
                    chunks[index].chunk_id,
                    [1.0, 0.0],
                    {
                        "content": chunks[index].content,
                        "document_id": chunks[index].document_id,
                        "document_version_id": chunks[index].document_version_id,
                        "logical_document_id": chunks[index].logical_document_id,
                        "chunk_id": chunks[index].chunk_id,
                        "citation_label": chunks[index].document_id,
                    },
                )
                for index in range(2)
            ),
            2,
        )
        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda current_workspace: original_reader(
                    current_workspace, settings=graph_settings
                )
            ),
        )
        factory = V2QueryServiceFactory(
            settings=graph_settings,
            qdrant_client=qdrant,
            planner_providers={"openai": _SemanticFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        service = factory.build(inputs)
        canonical = load_canonical_population(graph, generation.id, "person")
        canonical_merter_ids = {
            record.record_id
            for record in canonical.records
            if record.values.get("surname") == "Merter"
        }
        assert canonical.workspace_id == workspace_id
        assert canonical.generation_id == generation.id
        assert len(canonical.records) == 5
        assert len(canonical_merter_ids) == 5
        print(
            "top-k canonical population "
            f"workspace_id={canonical.workspace_id} generation_id={canonical.generation_id} "
            f"person_ids={sorted(record.record_id for record in canonical.records)} "
            f"merter_ids={sorted(canonical_merter_ids)}"
        )
        retrieval_visible = service.executor.dense.search(
            inputs.generation_scope, [1.0, 0.0], limit=30
        )
        counted = asyncio.run(
            service.execute_inputs(session, "Merter soyadlı kaç kişi var?", inputs)
        )

        assert len(canonical.records) == 5
        assert len(retrieval_visible) < len(canonical.records)
        assert len(retrieval_visible) == 2
        assert counted.package.aggregates[0].value == 5
        assert counted.answer.state == "corpus_complete"
        assert "count: 5" in counted.answer.content
        assert counted.trace.dense_result_count == 0
        assert all(trace.engine == "structured" for trace in counted.package.traces)
        assert {trace.capability for trace in counted.package.traces} == {"structured.count"}
    finally:
        graph.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        graph.close()
        session.close()


def test_live_count_uses_canonical_identity_not_alias_or_mention_cardinality(tmp_path, monkeypatch):
    """COUNT consumes canonical identities even when their source artifacts multiply."""
    workspace_id = f"canonical-dedup-count-{uuid4()}"
    graph_settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
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
    conversation_id = str(uuid4())
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Canonical dedup COUNT acceptance",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()

    source_texts = ("Ali Merter", "A. Merter", "Bora Merter", "B. Merter")
    generation = create_generation(session, workspace_id, "canonical-dedup-count-source")
    chunks = tuple(
        SourceChunk(
            f"chunk-{index}",
            f"document-{index}",
            f"version-{index}",
            f"logical-{index}",
            index,
            text,
            hashlib.sha256(text.encode()).hexdigest(),
        )
        for index, text in enumerate(source_texts)
    )
    snapshot = CorpusSnapshot(workspace_id, generation.source_fingerprint, chunks)
    manifest = write_generation_manifest(tmp_path, snapshot, generation.id)
    generation.source_manifest_uri, generation.source_manifest_hash = manifest.uri, manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    fingerprint = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2).fingerprint
    for stage in ("source_relational", "bm25", "dense_qdrant"):
        mark_stage_ready(
            session,
            generation,
            stage,
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint=stage,
            metrics={"embedding_config_hash": fingerprint},
        )
    mark_stage_ready(
        session,
        generation,
        "canonical_graph",
        input_fingerprint=generation.source_fingerprint,
        output_fingerprint="canonical",
        metrics={"resolved_entity_property_count": 2, "entity_property_schema_version": "1"},
    )
    generation.state = "active"
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=generation.id,
            source_fingerprint=generation.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()

    def mention_source(index):
        text = chunks[index].content
        return ExactSourceProvenance(
            workspace_id=workspace_id,
            document_id=chunks[index].document_id,
            document_version_id=chunks[index].document_version_id,
            logical_document_id=chunks[index].logical_document_id,
            chunk_id=chunks[index].chunk_id,
            start_offset=0,
            end_offset=len(text),
            source_text=text,
            extraction_run_id="canonical-dedup-count",
            provider="fixture",
            model="fixture",
            prompt_version="v1",
            schema_version="v1",
            confidence=1.0,
            validation_state="validated",
            generation=generation.id,
        )

    def surname_source(index):
        source = mention_source(index)
        start = source.source_text.index("Merter")
        return ExactSourceProvenance(
            workspace_id=source.workspace_id,
            document_id=source.document_id,
            document_version_id=source.document_version_id,
            logical_document_id=source.logical_document_id,
            chunk_id=source.chunk_id,
            start_offset=start,
            end_offset=start + len("Merter"),
            source_text="Merter",
            extraction_run_id=source.extraction_run_id,
            provider=source.provider,
            model=source.model,
            prompt_version=source.prompt_version,
            schema_version=source.schema_version,
            confidence=source.confidence,
            validation_state=source.validation_state,
            generation=source.generation,
        )

    graph = Neo4jGraphAdapter.from_settings(workspace_id, settings=graph_settings)
    try:
        graph.ensure_schema()
        e1, e2 = new_canonical_id(), new_canonical_id()
        entities = (
            CanonicalEntity(
                e1,
                EntityType.PERSON,
                "Ali Merter",
                KnowledgeAuthority.EXTRACTED,
                aliases=(
                    EntityAlias(new_canonical_id(), "A. Merter", KnowledgeAuthority.EXTRACTED),
                ),
                mentions=tuple(
                    EntityMention(
                        new_canonical_id(),
                        source_texts[index],
                        EntityType.PERSON,
                        mention_source(index),
                        resolved_entity_id=e1,
                        decision=IdentityDecisionKind.MANUAL_LINK,
                    )
                    for index in (0, 1)
                ),
            ),
            CanonicalEntity(
                e2,
                EntityType.PERSON,
                "Bora Merter",
                KnowledgeAuthority.EXTRACTED,
                aliases=(
                    EntityAlias(new_canonical_id(), "B. Merter", KnowledgeAuthority.EXTRACTED),
                ),
                mentions=tuple(
                    EntityMention(
                        new_canonical_id(),
                        source_texts[index],
                        EntityType.PERSON,
                        mention_source(index),
                        resolved_entity_id=e2,
                        decision=IdentityDecisionKind.MANUAL_LINK,
                    )
                    for index in (2, 3)
                ),
            ),
        )
        for entity, source_index in zip(entities, (0, 2), strict=True):
            graph.upsert_canonical_entity(entity, generation.id)
            graph.upsert_canonical_entity_property(
                CanonicalEntityProperty(
                    new_canonical_id(),
                    entity.entity_id,
                    "surname",
                    "Merter",
                    EntityPropertyValueType.STRING,
                    KnowledgeAuthority.EXTRACTED,
                    generation.id,
                    surname_source(source_index),
                )
            )

        mention_rows, _, _ = graph.driver.execute_query(
            "MATCH (m:CortexMention {workspace_id: $workspace_id})-[:RESOLVES_TO]->"
            "(:CortexNode:CanonicalKnowledge:CanonicalEntity {workspace_id: $workspace_id}) "
            "MATCH (m)-[:SUPPORTED_BY]->(:CortexEvidence {workspace_id: $workspace_id, "
            "generation: $generation}) RETURN count(DISTINCT m) AS count",
            workspace_id=workspace_id,
            generation=generation.id,
            database_=graph.database,
        )
        alias_rows, _, _ = graph.driver.execute_query(
            "MATCH (:CortexNode:CanonicalKnowledge:CanonicalEntity {workspace_id: $workspace_id})"
            "-[:HAS_ALIAS]->(a:CortexAlias {workspace_id: $workspace_id, active: true}) "
            "RETURN count(DISTINCT a) AS count",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        mention_count, alias_count = int(mention_rows[0]["count"]), int(alias_rows[0]["count"])
        assert mention_count == 4
        assert alias_count == 2

        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda current_workspace: original_reader(
                    current_workspace, settings=graph_settings
                )
            ),
        )
        factory = V2QueryServiceFactory(
            settings=graph_settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _SemanticFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        service = factory.build(inputs)
        canonical = load_canonical_population(graph, generation.id, "person")
        merter_ids = {
            record.record_id
            for record in canonical.records
            if record.values.get("surname") == "Merter"
        }
        assert canonical.workspace_id == workspace_id
        assert canonical.generation_id == generation.id
        assert merter_ids == {e1, e2}
        assert len(canonical.records) == 2
        assert mention_count > len(merter_ids)
        assert alias_count >= len(merter_ids)
        print(
            "canonical-dedup population "
            f"workspace_id={canonical.workspace_id} generation_id={canonical.generation_id} "
            f"person_ids={sorted(record.record_id for record in canonical.records)} "
            f"merter_ids={sorted(merter_ids)} "
            f"mention_count={mention_count} alias_count={alias_count}"
        )
        counted = asyncio.run(
            service.execute_inputs(session, "Merter soyadlı kaç kişi var?", inputs)
        )

        assert counted.package.aggregates[0].value == 2
        assert "count: 2" in counted.answer.content
        assert counted.answer.state == "corpus_complete"
        assert counted.trace.dense_result_count == 0
        assert {trace.engine for trace in counted.package.traces} == {"structured"}
        assert {trace.capability for trace in counted.package.traces} == {"structured.count"}
    finally:
        graph.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        graph.close()
        session.close()


def test_live_list_and_count_are_isolated_by_knowledge_generation(tmp_path, monkeypatch):
    """One workspace retains generation-specific canonical properties for V2 LIST/COUNT."""
    workspace_id = f"generation-isolation-{uuid4()}"
    graph_settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
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
    conversation_id = str(uuid4())
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Generation-isolated LIST/COUNT acceptance",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()

    def provision(label, surnames):
        generation = create_generation(session, workspace_id, f"generation-isolation-{label}")
        names = ("Ali", "Bora")
        chunks = tuple(
            SourceChunk(
                f"{label}-chunk-{index}",
                f"{label}-document-{index}",
                f"{label}-version-{index}",
                f"{label}-logical-{index}",
                index,
                f"{names[index]} {surnames[index]}",
                hashlib.sha256(f"{names[index]} {surnames[index]}".encode()).hexdigest(),
            )
            for index in range(2)
        )
        snapshot = CorpusSnapshot(workspace_id, generation.source_fingerprint, chunks)
        manifest = write_generation_manifest(tmp_path, snapshot, generation.id)
        generation.source_manifest_uri, generation.source_manifest_hash = (
            manifest.uri,
            manifest.sha256,
        )
        generation.source_chunk_count = manifest.chunk_count
        fingerprint = EmbeddingConfiguration(
            "ollama", "acceptance-embedding", dimension=2
        ).fingerprint
        for stage in ("source_relational", "bm25", "dense_qdrant"):
            mark_stage_ready(
                session,
                generation,
                stage,
                input_fingerprint=generation.source_fingerprint,
                output_fingerprint=f"{label}-{stage}",
                metrics={"embedding_config_hash": fingerprint},
            )
        mark_stage_ready(
            session,
            generation,
            "canonical_graph",
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint=f"{label}-canonical",
            metrics={"resolved_entity_property_count": 2, "entity_property_schema_version": "1"},
        )
        generation.state = "active"
        return generation, chunks

    g1, g1_chunks = provision("g1", ("Merter", "Kaya"))
    g2, g2_chunks = provision("g2", ("Kaya", "Kaya"))
    activation = QueryRuntimeActivation(
        workspace_id=workspace_id,
        runtime_version="v2",
        generation_id=g1.id,
        source_fingerprint=g1.source_fingerprint,
        evaluation_fingerprint=None,
        curation_fingerprint=None,
        activated_at=now,
        updated_at=now,
    )
    session.add(activation)
    session.flush()

    def provenance(generation, chunks, index, value):
        text = chunks[index].content
        start = text.index(value)
        return ExactSourceProvenance(
            workspace_id=workspace_id,
            document_id=chunks[index].document_id,
            document_version_id=chunks[index].document_version_id,
            logical_document_id=chunks[index].logical_document_id,
            chunk_id=chunks[index].chunk_id,
            start_offset=start,
            end_offset=start + len(value),
            source_text=value,
            extraction_run_id="generation-isolation",
            provider="fixture",
            model="fixture",
            prompt_version="v1",
            schema_version="v1",
            confidence=1.0,
            validation_state="validated",
            generation=generation.id,
        )

    graph = Neo4jGraphAdapter.from_settings(workspace_id, settings=graph_settings)
    try:
        graph.ensure_schema()
        e1, e2 = new_canonical_id(), new_canonical_id()
        for generation, chunks, surnames in (
            (g1, g1_chunks, ("Merter", "Kaya")),
            (g2, g2_chunks, ("Kaya", "Kaya")),
        ):
            for index, (entity_id, display_name, surname) in enumerate(
                ((e1, "Ali", surnames[0]), (e2, "Bora", surnames[1]))
            ):
                mention_text = chunks[index].content
                graph.upsert_canonical_entity(
                    CanonicalEntity(
                        entity_id,
                        EntityType.PERSON,
                        display_name,
                        KnowledgeAuthority.EXTRACTED,
                        mentions=(
                            EntityMention(
                                new_canonical_id(),
                                mention_text,
                                EntityType.PERSON,
                                provenance(generation, chunks, index, mention_text),
                                resolved_entity_id=entity_id,
                                decision=IdentityDecisionKind.MANUAL_LINK,
                            ),
                        ),
                    ),
                    generation.id,
                )
                graph.upsert_canonical_entity_property(
                    CanonicalEntityProperty(
                        new_canonical_id(),
                        entity_id,
                        "surname",
                        surname,
                        EntityPropertyValueType.STRING,
                        KnowledgeAuthority.EXTRACTED,
                        generation.id,
                        provenance(generation, chunks, index, surname),
                    )
                )

        g1_population = load_canonical_population(graph, g1.id, "person")
        g2_population = load_canonical_population(graph, g2.id, "person")
        g1_merter_ids = {
            record.record_id
            for record in g1_population.records
            if record.values.get("surname") == "Merter"
        }
        g2_merter_ids = {
            record.record_id
            for record in g2_population.records
            if record.values.get("surname") == "Merter"
        }
        assert g1_population.workspace_id == g2_population.workspace_id == workspace_id
        assert g1_population.generation_id == g1.id
        assert g2_population.generation_id == g2.id
        assert g1_merter_ids == {e1}
        assert g2_merter_ids == set()
        assert {record.record_id for record in g1_population.records} == {e1, e2}
        assert {record.record_id for record in g2_population.records} == {e1, e2}

        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda current_workspace: original_reader(
                    current_workspace, settings=graph_settings
                )
            ),
        )
        factory = V2QueryServiceFactory(
            settings=graph_settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _SemanticFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        g1_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        activation.generation_id = g2.id
        activation.source_fingerprint = g2.source_fingerprint
        session.flush()
        g2_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        assert g1_inputs.generation_scope.workspace_id == g2_inputs.generation_scope.workspace_id
        assert g1_inputs.generation_scope.workspace_id == workspace_id
        assert g1_inputs.generation_scope.generation_id == g1.id
        assert g2_inputs.generation_scope.generation_id == g2.id

        g1_service, g2_service = factory.build(g1_inputs), factory.build(g2_inputs)
        assert g1_service.property_vocabulary_loader(g1_inputs.generation_scope) == {
            "person": frozenset({"surname"})
        }
        assert g2_service.property_vocabulary_loader(g2_inputs.generation_scope) == {
            "person": frozenset({"surname"})
        }
        g1_list = asyncio.run(
            g1_service.execute_inputs(session, "Merter soyadlı kişiler kimler?", g1_inputs)
        )
        g2_list = asyncio.run(
            g2_service.execute_inputs(session, "Merter soyadlı kişiler kimler?", g2_inputs)
        )
        activation.generation_id = g1.id
        activation.source_fingerprint = g1.source_fingerprint
        session.flush()
        _, g1_assistant, g1_run = asyncio.run(
            execute_v2_chat(
                session,
                workspace_id,
                conversation_id,
                "Merter soyadlı kaç kişi var?",
                "automatic",
                factory=factory,
            )
        )
        activation.generation_id = g2.id
        activation.source_fingerprint = g2.source_fingerprint
        session.flush()
        _, g2_assistant, g2_run = asyncio.run(
            execute_v2_chat(
                session,
                workspace_id,
                conversation_id,
                "Merter soyadlı kaç kişi var?",
                "automatic",
                factory=factory,
            )
        )
        g1_count_metadata = json.loads(g1_assistant.metadata_json)
        g2_count_metadata = json.loads(g2_assistant.metadata_json)

        assert {item.item_id for item in g1_list.package.structured_rows} == {e1}
        assert g2_list.package.structured_rows == ()
        assert g1_list.trace.generation_id == g1.id
        assert g2_list.trace.generation_id == g2.id
        assert g1_list.package.generation_id == g1.id
        assert g2_list.package.generation_id == g2.id
        assert g1_list.package.completeness.generation_id == g1.id
        assert g2_list.package.completeness.generation_id == g2.id
        assert {trace.engine for trace in g1_list.package.traces} == {"structured"}
        assert {trace.engine for trace in g2_list.package.traces} == {"structured"}
        assert g1_count_metadata["generation_id"] == g1.id
        assert g2_count_metadata["generation_id"] == g2.id
        assert g1_count_metadata["reasoning_package_generation"] == g1.id
        assert g2_count_metadata["reasoning_package_generation"] == g2.id
        assert g1_count_metadata["execution_trace"]["answer_status"] == "corpus_complete"
        assert g2_count_metadata["execution_trace"]["answer_status"] == "corpus_complete"
        assert "structured.count" in {
            step["capability"] for step in g1_count_metadata["query_plan"]["graph"]["steps"]
        }
        assert "structured.count" in {
            step["capability"] for step in g2_count_metadata["query_plan"]["graph"]["steps"]
        }
        assert "count: 1" in g1_assistant.content
        assert "count: 0" in g2_assistant.content
        assert g1_run.state == g2_run.state == "completed"
        assert {trace.capability for trace in g1_list.package.traces} == {"structured.filter"}
        assert {trace.capability for trace in g2_list.package.traces} == {"structured.filter"}
        print(
            "generation-isolation "
            f"workspace_id={workspace_id} g1={g1.id} g2={g2.id} e1={e1} e2={e2} "
            f"g1_merter_ids={sorted(g1_merter_ids)} g2_merter_ids={sorted(g2_merter_ids)}"
        )
    finally:
        graph.driver.execute_query(
            "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
            workspace_id=workspace_id,
            database_=graph.database,
        )
        graph.close()
        session.close()


def test_live_natural_language_list_count_and_persisted_chat_acceptance(tmp_path, monkeypatch):
    """Full production LIST/COUNT path over real Neo4j canonical projections."""
    workspace_a, workspace_b = f"list-count-a-{uuid4()}", f"list-count-b-{uuid4()}"
    graph_settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
    for workspace_id in (workspace_a, workspace_b):
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
    conversation_id = str(uuid4())
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_a,
            title="E2E",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()

    def provision(workspace_id, names):
        generation = create_generation(session, workspace_id, f"source-{workspace_id}")
        chunks = tuple(
            SourceChunk(
                f"chunk-{index}",
                f"doc-{index}",
                f"version-{index}",
                f"logical-{index}",
                index,
                name,
                hashlib.sha256(name.encode()).hexdigest(),
            )
            for index, name in enumerate(names)
        )
        snapshot = CorpusSnapshot(workspace_id, generation.source_fingerprint, chunks)
        manifest = write_generation_manifest(tmp_path, snapshot, generation.id)
        generation.source_manifest_uri, generation.source_manifest_hash = (
            manifest.uri,
            manifest.sha256,
        )
        generation.source_chunk_count = manifest.chunk_count
        fingerprint = EmbeddingConfiguration(
            "ollama", "acceptance-embedding", dimension=2
        ).fingerprint
        for stage in ("source_relational", "bm25", "dense_qdrant"):
            mark_stage_ready(
                session,
                generation,
                stage,
                input_fingerprint=generation.source_fingerprint,
                output_fingerprint=stage,
                metrics={"embedding_config_hash": fingerprint},
            )
        mark_stage_ready(
            session,
            generation,
            "canonical_graph",
            input_fingerprint=generation.source_fingerprint,
            output_fingerprint="canonical",
            metrics={"resolved_entity_property_count": 2, "entity_property_schema_version": "1"},
        )
        generation.state = "active"
        return generation, chunks

    generation, chunks = provision(
        workspace_a,
        ("Ali Merter", "Ayşe Merter", "Mehmet Kaya", "Fake Merter", "Ali Merter Mertel"),
    )
    provision(workspace_b, ("Foreign Merter",))
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_a,
            runtime_version="v2",
            generation_id=generation.id,
            source_fingerprint=generation.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()

    adapters = [
        Neo4jGraphAdapter.from_settings(workspace_a, settings=graph_settings),
        Neo4jGraphAdapter.from_settings(workspace_b, settings=graph_settings),
    ]

    def source(index, generation_id=generation.id, workspace_id=workspace_a):
        text = chunks[index].content
        return ExactSourceProvenance(
            workspace_id=workspace_id,
            document_id=chunks[index].document_id,
            document_version_id=chunks[index].document_version_id,
            logical_document_id=chunks[index].logical_document_id,
            chunk_id=chunks[index].chunk_id,
            start_offset=0,
            end_offset=len(text),
            source_text=text,
            extraction_run_id="e2e",
            provider="fixture",
            model="fixture",
            prompt_version="v1",
            schema_version="v1",
            confidence=1.0,
            validation_state="validated",
            generation=generation_id,
        )

    try:
        graph = adapters[0]
        graph.ensure_schema()
        ids = []
        for index, (name, surname) in enumerate(
            (
                ("Ali Merter", "Merter"),
                ("Ayşe Merter", "Merter"),
                ("Mehmet Subasi", "Subasi"),
                ("Fake Merter", None),
                ("Ali Merter Mertel", None),
            )
        ):
            entity = CanonicalEntity.create(
                EntityType.PERSON,
                name,
                mentions=(
                    EntityMention(new_canonical_id(), name, EntityType.PERSON, source(index)),
                ),
            )
            graph.upsert_canonical_entity(entity, generation.id)
            ids.append(entity.entity_id)
            if surname:
                graph.upsert_canonical_entity_property(
                    CanonicalEntityProperty(
                        new_canonical_id(),
                        entity.entity_id,
                        "surname",
                        surname,
                        EntityPropertyValueType.STRING,
                        KnowledgeAuthority.EXTRACTED,
                        generation.id,
                        source(index),
                    )
                )
        for value in ("Merter", "Mertel"):
            graph.upsert_canonical_entity_property(
                CanonicalEntityProperty(
                    new_canonical_id(),
                    ids[4],
                    "surname",
                    value,
                    EntityPropertyValueType.STRING,
                    KnowledgeAuthority.EXTRACTED,
                    generation.id,
                    source(4),
                    status="conflicted",
                )
            )
        foreign = adapters[1]
        foreign.ensure_schema()
        foreign_generation = (
            session.query(type(generation)).filter_by(workspace_id=workspace_b).one().id
        )
        foreign_entity = CanonicalEntity.create(
            EntityType.PERSON,
            "Foreign Merter",
            mentions=(
                EntityMention(
                    new_canonical_id(),
                    "Foreign Merter",
                    EntityType.PERSON,
                    ExactSourceProvenance(
                        workspace_b,
                        "doc-0",
                        "version-0",
                        "logical-0",
                        "chunk-0",
                        0,
                        14,
                        "Foreign Merter",
                        "e2e",
                        "fixture",
                        "fixture",
                        "v1",
                        "v1",
                        1.0,
                        "validated",
                        foreign_generation,
                    ),
                ),
            ),
        )
        foreign.upsert_canonical_entity(foreign_entity, foreign_generation)
        foreign.upsert_canonical_entity_property(
            CanonicalEntityProperty(
                new_canonical_id(),
                foreign_entity.entity_id,
                "surname",
                "Merter",
                EntityPropertyValueType.STRING,
                KnowledgeAuthority.EXTRACTED,
                foreign_generation,
                ExactSourceProvenance(
                    workspace_b,
                    "doc-0",
                    "version-0",
                    "logical-0",
                    "chunk-0",
                    0,
                    14,
                    "Foreign Merter",
                    "e2e",
                    "fixture",
                    "fixture",
                    "v1",
                    "v1",
                    1.0,
                    "validated",
                    foreign_generation,
                ),
            )
        )

        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda workspace_id: original_reader(workspace_id, settings=graph_settings)
            ),
        )
        factory = V2QueryServiceFactory(
            settings=graph_settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _SemanticFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        inputs = factory.context_loader.load(session, workspace_a, conversation_id)
        service = factory.build(inputs)
        canonical = load_canonical_population(graph, generation.id, "person")
        canonical_merter_ids = {
            record.record_id
            for record in canonical.records
            if record.values.get("surname") == "Merter"
        }
        assert canonical.workspace_id == workspace_a
        assert canonical.generation_id == generation.id
        assert {record.record_id for record in canonical.records} == set(ids)
        assert canonical_merter_ids == set(ids[:2])
        print(
            "list-count canonical population "
            f"workspace_id={canonical.workspace_id} generation_id={canonical.generation_id} "
            f"person_ids={sorted(record.record_id for record in canonical.records)} "
            f"merter_ids={sorted(canonical_merter_ids)}"
        )
        listed = asyncio.run(
            service.execute_inputs(session, "Merter soyadlı kişiler kimler?", inputs)
        )
        counted = asyncio.run(
            service.execute_inputs(session, "Merter soyadlı kaç kişi var?", inputs)
        )
        zero = asyncio.run(service.execute_inputs(session, "Demir soyadlı kaç kişi var?", inputs))
        analytics_factory = V2QueryServiceFactory(
            settings=graph_settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _AnalyticsFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        analytics_inputs = analytics_factory.context_loader.load(
            session, workspace_a, conversation_id
        )
        analytics = analytics_factory.build(analytics_inputs)
        grouped = asyncio.run(
            analytics.execute_inputs(session, "group people by surname", analytics_inputs)
        )
        ranked = asyncio.run(
            analytics.execute_inputs(session, "rank surnames by person count", analytics_inputs)
        )
        compared = asyncio.run(
            analytics.execute_inputs(session, "compare Merter and Subasi people", analytics_inputs)
        )
        assert listed.prepared.semantic.understanding.structured_operation == "list"
        assert listed.prepared.semantic.understanding.typed_filters[0].property == "surname"
        assert {item.item_id for item in listed.package.structured_rows} == set(ids[:2])
        assert listed.package.completeness.state == "complete"
        assert listed.answer.state == "corpus_complete"
        assert counted.package.aggregates[0].value == 2
        assert counted.package.completeness.state == "complete"
        assert counted.trace.dense_result_count == counted.trace.sparse_result_count == 0
        assert zero.package.aggregates[0].value == 0
        assert zero.answer.state == "corpus_complete"
        assert all(trace.engine == "structured" for trace in counted.package.traces)
        assert {
            item.values["surname"]: item.values["confirmed_count"]
            for item in grouped.package.structured_rows
        } == {"Merter": 2, "Subasi": 1}
        assert [
            (item.values["surname"], item.values["confirmed_count"])
            for item in ranked.package.structured_rows
        ] == [("Merter", 2), ("Subasi", 1)]
        assert compared.package.structured_rows[0].values["result"] == {"left": 2, "right": 1}
        assert all(trace.engine == "structured" for trace in grouped.package.traces)
        assert all(trace.engine == "structured" for trace in ranked.package.traces)
        assert all(trace.engine == "structured" for trace in compared.package.traces)
        assert grouped.trace.dense_result_count == grouped.trace.sparse_result_count == 0
        assert ranked.trace.dense_result_count == ranked.trace.sparse_result_count == 0
        assert compared.trace.dense_result_count == compared.trace.sparse_result_count == 0
        _, assistant, run = asyncio.run(
            execute_v2_chat(
                session,
                workspace_a,
                conversation_id,
                "Merter soyadlı kaç kişi var?",
                "automatic",
                factory=factory,
            )
        )
        metadata = json.loads(assistant.metadata_json)
        assert run.state == "completed" and assistant.status == "completed"
        assert metadata["runtime"] == "v2" and metadata["generation_id"] == generation.id
        assert metadata["execution_trace"]["answer_status"] == "corpus_complete"
    finally:
        for adapter, workspace_id in zip(adapters, (workspace_a, workspace_b), strict=True):
            adapter.driver.execute_query(
                "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
                workspace_id=workspace_id,
                database_=adapter.database,
            )
            adapter.close()
        session.close()


def test_live_natural_language_relation_traversal_uses_canonical_graph(tmp_path, monkeypatch):
    """Direct parent_of traversal is graph-authoritative and generation-bound."""
    workspace_id, foreign_workspace = f"relation-a-{uuid4()}", f"relation-b-{uuid4()}"
    settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
    conversation_id = str(uuid4())
    for item in (workspace_id, foreign_workspace):
        session.add(
            Workspace(id=item, slug=item, name=item, state="active", created_at=now, updated_at=now)
        )
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Relations",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()

    fingerprint = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2).fingerprint

    def provision(label, names):
        generation = create_generation(session, workspace_id, f"relation-{label}")
        chunks = tuple(
            SourceChunk(
                f"{label}-chunk-{index}",
                f"{label}-doc-{index}",
                f"{label}-version-{index}",
                f"{label}-logical-{index}",
                index,
                name,
                hashlib.sha256(name.encode()).hexdigest(),
            )
            for index, name in enumerate(names)
        )
        manifest = write_generation_manifest(
            tmp_path,
            CorpusSnapshot(workspace_id, generation.source_fingerprint, chunks),
            generation.id,
        )
        generation.source_manifest_uri, generation.source_manifest_hash = (
            manifest.uri,
            manifest.sha256,
        )
        generation.source_chunk_count = manifest.chunk_count
        for stage in ("source_relational", "bm25", "dense_qdrant", "canonical_graph"):
            mark_stage_ready(
                session,
                generation,
                stage,
                input_fingerprint=generation.source_fingerprint,
                output_fingerprint=stage,
                metrics={"embedding_config_hash": fingerprint},
            )
        generation.state = "active"
        return generation, chunks

    g1, g1_chunks = provision("g1", ("Parent A parent of Child One", "Child One"))
    g2, g2_chunks = provision(
        "g2",
        (
            "Parent A parent of Child One",
            "Parent A parent of Child Two",
            "Child One parent of Grandchild One",
            "Child Two parent of Grandchild Two",
        ),
    )
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=g1.id,
            source_fingerprint=g1.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()
    adapter = Neo4jGraphAdapter.from_settings(workspace_id, settings=settings)
    foreign = Neo4jGraphAdapter.from_settings(foreign_workspace, settings=settings)

    parent_id, child_one_id, child_two_id, grandchild_one_id, grandchild_two_id, unrelated_id = (
        new_canonical_id() for _ in range(6)
    )

    def provenance(generation, chunks, index):
        chunk = chunks[index]
        return ExactSourceProvenance(
            workspace_id,
            chunk.document_id,
            chunk.document_version_id,
            chunk.logical_document_id,
            chunk.chunk_id,
            0,
            len(chunk.content),
            chunk.content,
            "relation-e2e",
            "fixture",
            "fixture",
            "v1",
            "v1",
            1.0,
            "validated",
            generation.id,
        )

    def entity(entity_id, name, generation, chunks, index):
        return CanonicalEntity(
            entity_id,
            EntityType.PERSON,
            name,
            KnowledgeAuthority.EXTRACTED,
            mentions=(
                EntityMention(
                    new_canonical_id(),
                    name,
                    EntityType.PERSON,
                    provenance(generation, chunks, index),
                ),
            ),
        )

    try:
        adapter.ensure_schema()
        for generation, chunks, rows in (
            (
                g1,
                g1_chunks,
                (
                    (parent_id, "Parent A", 0),
                    (child_one_id, "Child One", 1),
                    (unrelated_id, "Unrelated", 1),
                ),
            ),
            (
                g2,
                g2_chunks,
                (
                    (parent_id, "Parent A", 0),
                    (child_one_id, "Child One", 0),
                    (child_two_id, "Child Two", 2),
                    (grandchild_one_id, "Grandchild One", 2),
                    (grandchild_two_id, "Grandchild Two", 3),
                    (unrelated_id, "Unrelated", 2),
                ),
            ),
        ):
            for item_id, name, index in rows:
                adapter.upsert_canonical_entity(
                    entity(item_id, name, generation, chunks, index), generation.id
                )
        adapter.upsert_relation(
            CanonicalRelation(
                new_canonical_id(),
                parent_id,
                child_one_id,
                "parent_of",
                KnowledgeAuthority.EXTRACTED,
                g1.id,
                RelationSupport.EXACT_SPAN,
                (provenance(g1, g1_chunks, 0),),
                {},
            )
        )
        adapter.upsert_relation(
            CanonicalRelation(
                new_canonical_id(),
                child_one_id,
                grandchild_one_id,
                "parent_of",
                KnowledgeAuthority.EXTRACTED,
                g2.id,
                RelationSupport.EXACT_SPAN,
                (provenance(g2, g2_chunks, 2),),
                {},
            )
        )
        adapter.upsert_relation(
            CanonicalRelation(
                new_canonical_id(),
                child_two_id,
                grandchild_two_id,
                "parent_of",
                KnowledgeAuthority.EXTRACTED,
                g2.id,
                RelationSupport.EXACT_SPAN,
                (provenance(g2, g2_chunks, 3),),
                {},
            )
        )
        adapter.upsert_relation(
            CanonicalRelation(
                new_canonical_id(),
                parent_id,
                child_one_id,
                "parent_of",
                KnowledgeAuthority.EXTRACTED,
                g2.id,
                RelationSupport.EXACT_SPAN,
                (provenance(g2, g2_chunks, 0),),
                {},
            )
        )
        adapter.upsert_relation(
            CanonicalRelation(
                new_canonical_id(),
                parent_id,
                child_two_id,
                "parent_of",
                KnowledgeAuthority.EXTRACTED,
                g2.id,
                RelationSupport.EXACT_SPAN,
                (provenance(g2, g2_chunks, 1),),
                {},
            )
        )

        foreign.ensure_schema()
        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda scoped_workspace: original_reader(scoped_workspace, settings=settings)
            ),
        )
        factory = V2QueryServiceFactory(
            settings=settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _RelationTraversalFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        g1_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        session.get(QueryRuntimeActivation, workspace_id).generation_id = g2.id
        session.flush()
        g2_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        service_g1, service_g2 = factory.build(g1_inputs), factory.build(g2_inputs)
        query = "Parent A'nÄ±n Ã§ocuklarÄ± kim?"
        g1_result = asyncio.run(service_g1.execute_inputs(session, query, g1_inputs))
        g2_result = asyncio.run(service_g2.execute_inputs(session, query, g2_inputs))

        for result, generation, expected in (
            (g1_result, g1, {child_one_id}),
            (g2_result, g2, {child_one_id, child_two_id}),
        ):
            semantic = result.prepared.semantic.understanding
            assert semantic.relations[0].predicate == "parent_of"
            assert semantic.relations[0].direction == "outgoing"
            assert semantic.relations[0].target_entity_type == "person"
            assert semantic.entities[0].canonical_entity_id == parent_id
            traverse = next(
                node for node in result.prepared.logical_ir.nodes if node.kind == "traverse"
            )
            assert traverse.relation.relation == "parent_of" and traverse.direction == "outgoing"
            plan_step = next(
                step
                for step in result.prepared.physical_plan.graph.steps
                if step.step_id == f"execute.{traverse.node_id}"
            )
            assert (
                plan_step.engine == "knowledge_graph" and plan_step.capability == "graph.traverse"
            )
            assert {item.entity_id for item in result.package.entities} == expected
            assert {path.node_ids[-1] for path in result.package.graph_paths} == expected
            assert all(trace.engine == "knowledge_graph" for trace in result.package.traces)
            assert result.trace.dense_result_count == result.trace.sparse_result_count == 0
            assert result.package.generation_id == generation.id
        assert unrelated_id not in {item.entity_id for item in g2_result.package.entities}
        assert "Child One" in g2_result.answer.content and "Child Two" in g2_result.answer.content
        assert "Unrelated" not in g2_result.answer.content
        activation = session.get(QueryRuntimeActivation, workspace_id)
        activation.generation_id = g2.id
        activation.source_fingerprint = g2.source_fingerprint
        session.flush()
        _, q1_assistant, _ = asyncio.run(
            execute_v2_chat(
                session,
                workspace_id,
                conversation_id,
                "Parent A'nÄ±n Ã§ocuklarÄ± kim?",
                "automatic",
                factory=factory,
            )
        )
        _, q2_assistant, _ = asyncio.run(
            execute_v2_chat(
                session,
                workspace_id,
                conversation_id,
                "OnlarÄ±n Ã§ocuklarÄ± kim?",
                "automatic",
                factory=factory,
            )
        )
        persisted_context = factory.context_loader.load(
            session, workspace_id, conversation_id
        ).conversation_context
        q2_metadata = json.loads(q2_assistant.metadata_json)
        q2_resolve = next(
            node for node in q2_metadata["logical_ir"]["nodes"] if node["kind"] == "resolve"
        )
        assert persisted_context.state.last_final_entity_result is not None
        assert set(persisted_context.state.last_final_entity_result.canonical_entity_ids) == {
            grandchild_one_id,
            grandchild_two_id,
        }
        assert persisted_context.state.last_final_entity_result.generation_id == g2.id
        assert set(q2_resolve["canonical_entity_ids"]) == {child_one_id, child_two_id}
        assert "Child One" in q1_assistant.content and "Child Two" in q1_assistant.content
        assert "Grandchild One" in q2_assistant.content and "Grandchild Two" in q2_assistant.content
        assert "Unrelated" not in q2_assistant.content
    finally:
        for graph, scoped_workspace in ((adapter, workspace_id), (foreign, foreign_workspace)):
            graph.driver.execute_query(
                "MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
                workspace_id=scoped_workspace,
                database_=graph.database,
            )
            graph.close()
        session.close()


def test_live_natural_language_exact_event_date_is_generation_bound_and_graph_authoritative(
    tmp_path, monkeypatch
):
    """Exact event membership uses canonical event_date, never document dates or retrieval."""
    workspace_id, foreign_workspace = f"event-a-{uuid4()}", f"event-b-{uuid4()}"
    settings = Settings(
        data_path=tmp_path,
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="cortex-local-neo4j",
        embedding_provider="ollama",
        embedding_model="acceptance-embedding",
        semantic_planner_escalation_enabled=False,
        semantic_planner_repair_attempts=0,
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()
    now = datetime.now(UTC)
    conversation_id = str(uuid4())
    for workspace in (workspace_id, foreign_workspace):
        session.add(
            Workspace(
                id=workspace,
                slug=workspace,
                name=workspace,
                state="active",
                created_at=now,
                updated_at=now,
            )
        )
    session.add(
        Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            title="Events",
            summary=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.flush()
    fingerprint = EmbeddingConfiguration("ollama", "acceptance-embedding", dimension=2).fingerprint

    def provision(workspace, label, texts):
        generation = create_generation(session, workspace, f"events-{label}")
        chunks = tuple(
            SourceChunk(
                f"{label}-chunk-{index}",
                f"{label}-doc-{index}",
                f"{label}-version-{index}",
                f"{label}-logical-{index}",
                index,
                text,
                hashlib.sha256(text.encode()).hexdigest(),
            )
            for index, text in enumerate(texts)
        )
        manifest = write_generation_manifest(
            tmp_path,
            CorpusSnapshot(workspace, generation.source_fingerprint, chunks),
            generation.id,
        )
        generation.source_manifest_uri = manifest.uri
        generation.source_manifest_hash = manifest.sha256
        generation.source_chunk_count = manifest.chunk_count
        for stage in ("source_relational", "bm25", "dense_qdrant", "canonical_graph"):
            mark_stage_ready(
                session,
                generation,
                stage,
                input_fingerprint=generation.source_fingerprint,
                output_fingerprint=stage,
                metrics={"embedding_config_hash": fingerprint},
            )
        generation.state = "active"
        return generation, chunks

    g1, g1_chunks = provision(workspace_id, "g1", (
        "E1 occurred on 1974-06-12.", "E2 occurred on 1974-06-13.",
        "E3 occurred on 1974-06-11; document date 1974-06-12.",
    ))
    g2, g2_chunks = provision(workspace_id, "g2", (
        "E1 remains visible on 1974-06-12.", "E4 occurred on 1974-06-12.",
    ))
    foreign_generation, foreign_chunks = provision(
        foreign_workspace, "w2", ("W2 occurred on 1974-06-12.",)
    )
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=g1.id,
            source_fingerprint=g1.source_fingerprint,
            evaluation_fingerprint=None,
            curation_fingerprint=None,
            activated_at=now,
            updated_at=now,
        )
    )
    session.flush()
    adapters = (
        Neo4jGraphAdapter.from_settings(workspace_id, settings=settings),
        Neo4jGraphAdapter.from_settings(foreign_workspace, settings=settings),
    )

    def source(generation, chunks, index, workspace=workspace_id):
        chunk = chunks[index]
        return ExactSourceProvenance(
            workspace,
            chunk.document_id,
            chunk.document_version_id,
            chunk.logical_document_id,
            chunk.chunk_id,
            0,
            len(chunk.content),
            chunk.content,
            "event-e2e",
            "fixture",
            "fixture",
            "v1",
            "v1",
            1.0,
            "validated",
            generation.id,
        )

    def add_event(
        adapter, generation, chunks, index, event_id, name, event_date, workspace=workspace_id
    ):
        temporal_id = new_canonical_id()
        event = CanonicalEvent(
            event_id,
            "historical_event",
            name,
            KnowledgeAuthority.EXTRACTED,
            generation.id,
            (),
            (source(generation, chunks, index, workspace),),
            (temporal_id,),
        )
        adapter.upsert_event(event)
        adapter.upsert_temporal(
            TemporalExpression(
                temporal_id,
                event_date,
                event_date,
                event_date,
                "event_date",
                TemporalPrecision.DAY,
                False,
                generation.id,
                source(generation, chunks, index, workspace),
            )
        )

    e1, e2, e3, e4, w2 = (new_canonical_id() for _ in range(5))
    try:
        for adapter in adapters:
            adapter.ensure_schema()
        add_event(adapters[0], g1, g1_chunks, 0, e1, "E1", "1974-06-12")
        add_event(adapters[0], g1, g1_chunks, 1, e2, "E2", "1974-06-13")
        add_event(adapters[0], g1, g1_chunks, 2, e3, "E3", "1974-06-11")
        add_event(adapters[0], g2, g2_chunks, 0, e1, "E1", "1974-06-12")
        add_event(adapters[0], g2, g2_chunks, 1, e4, "E4", "1974-06-12")
        add_event(
            adapters[1],
            foreign_generation,
            foreign_chunks,
            0,
            w2,
            "W2",
            "1974-06-12",
            foreign_workspace,
        )
        original_reader = Neo4jGraphAdapter.from_settings
        monkeypatch.setattr(
            "app.query.production.Neo4jGraphAdapter.from_settings",
            staticmethod(
                lambda scoped_workspace: original_reader(scoped_workspace, settings=settings)
            ),
        )
        factory = V2QueryServiceFactory(
            settings=settings,
            qdrant_client=QdrantClient(":memory:"),
            planner_providers={"openai": _ExactDateEventFixtureProvider()},
            embedding_provider=_EmbeddingFixtureProvider(),
        )
        g1_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        activation = session.get(QueryRuntimeActivation, workspace_id)
        activation.generation_id, activation.source_fingerprint = g2.id, g2.source_fingerprint
        session.flush()
        g2_inputs = factory.context_loader.load(session, workspace_id, conversation_id)
        query = "12.06.1974 tarihinde ne olmuÅŸtu?"
        g1_result = asyncio.run(
            factory.build(g1_inputs).execute_inputs(session, query, g1_inputs)
        )
        g2_result = asyncio.run(
            factory.build(g2_inputs).execute_inputs(session, query, g2_inputs)
        )
        for result, generation, expected in ((g1_result, g1, {e1}), (g2_result, g2, {e1, e4})):
            semantic = result.prepared.semantic.understanding
            assert semantic.temporal_constraints[0].normalized_start == "1974-06-12"
            assert semantic.temporal_constraints[0].role == "event_date"
            assert [node.kind for node in result.prepared.logical_ir.nodes[:2]] == [
                "event_set",
                "temporal_constraint",
            ]
            assert "graph.event_filter" in [
                step.capability for step in result.prepared.physical_plan.graph.steps
            ]
            assert {event.event_id for event in result.package.events} == expected
            assert result.trace.dense_result_count == result.trace.sparse_result_count == 0
            assert all(trace.capability != "retrieval.search" for trace in result.package.traces)
            assert all(trace.engine == "knowledge_graph" for trace in result.package.traces)
            assert result.package.generation_id == generation.id
        assert e2 not in {event.event_id for event in g2_result.package.events}
        assert e3 not in {event.event_id for event in g2_result.package.events}
        assert w2 not in {event.event_id for event in g2_result.package.events}
        empty = asyncio.run(factory.build(g2_inputs).execute_inputs(
            session, "14.06.1974 tarihinde ne olmuÅŸtu?", g2_inputs
        ))
        assert empty.package.events == () and empty.answer.state == "unsupported"
        with pytest.raises(SemanticPlannerOutputError):
            asyncio.run(factory.build(g2_inputs).execute_inputs(
                session, "31.02.1974 tarihinde ne olmuÅŸtu?", g2_inputs
            ))
    finally:
        for adapter, workspace in zip(adapters, (workspace_id, foreign_workspace), strict=True):
            adapter.driver.execute_query("MATCH (n {workspace_id: $workspace_id}) DETACH DELETE n",
                                         workspace_id=workspace, database_=adapter.database)
            adapter.close()
        session.close()
