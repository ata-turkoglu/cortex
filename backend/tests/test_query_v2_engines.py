from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from app.engines.graph import GraphExecutionError, GraphValue, KnowledgeGraphEngine
from app.engines.structured import (
    CanonicalPopulation,
    CanonicalRecord,
    StructuredQueryEngine,
    load_canonical_population,
)
from app.knowledge.graph import (
    CanonicalConflictQueryView,
    CanonicalEntityQueryView,
    CanonicalEventQueryView,
    CanonicalEvidenceQueryView,
    CanonicalPathQueryView,
    CanonicalPopulationQueryView,
    Neo4jGraphAdapter,
)
from app.knowledge.model import KnowledgeAuthority
from app.knowledge.provenance import ExactSourceProvenance
from app.knowledge.relations import CanonicalRelation, RelationSupport
from app.query.answer import AnswerEngine
from app.query.ir import (
    AggregateNode,
    CompareNode,
    CountNode,
    CustomCapabilityNode,
    DistinctNode,
    FieldReference,
    FilterNode,
    GroupNode,
    ProjectionField,
    ProjectNode,
    RankNode,
    RelationAggregateNode,
    RelationReference,
    ResolveNode,
    ScanNode,
    TemporalConstraintNode,
    TemporalPredicate,
    TraverseNode,
)
from app.query.orchestration import (
    CompletenessReport,
    ExactEvidenceSpan,
    GroundedItem,
    ReasoningPackage,
)
from app.query.planning import (
    ExecutionStep,
    FailurePolicy,
    PlanTrace,
    ReadinessRequirement,
)

WORKSPACE = "workspace-1"
GENERATION = "generation-7"


def _evidence(evidence_id: str, text: str = "Merter owns parcel 42") -> ExactEvidenceSpan:
    return ExactEvidenceSpan(
        evidence_id=evidence_id,
        workspace_id=WORKSPACE,
        document_id=f"document-{evidence_id}",
        document_version_id=f"version-{evidence_id}",
        logical_document_id=f"logical-{evidence_id}",
        chunk_id=f"chunk-{evidence_id}",
        start_offset=0,
        end_offset=len(text),
        source_text=text,
        generation_id=GENERATION,
        relevance_score=0.9,
        quality_score=0.9,
    )


def _step(engine: str, capability: str, node_id: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=f"execute.{node_id}",
        engine=engine,
        capability=capability,
        output_type="extension" if capability.startswith("graph.") else "record_set",
        coverage_expectation="exhaustive" if engine == "structured" else "grounded",
        readiness=ReadinessRequirement(
            workspace_id=WORKSPACE,
            generation_id=GENERATION,
        ),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(
            logical_node_ids=(node_id,),
            selection_reason="test capability selection",
        ),
    )


def _population(*, safe: bool = True) -> CanonicalPopulation:
    records = (
        CanonicalRecord(
            record_id="person-1",
            resource="person",
            values={"display_name": "Ali Merter", "surname": "Merter", "score": 8},
            evidence=(_evidence("evidence-1"),),
        ),
        CanonicalRecord(
            record_id="person-2",
            resource="person",
            values={"display_name": "Ayşe Merter", "surname": "Merter", "score": 12},
            evidence=(_evidence("evidence-2"),),
        ),
        CanonicalRecord(
            record_id="person-3",
            resource="person",
            values={"display_name": "Deniz Kaya", "surname": "Kaya", "score": 4},
            evidence=(_evidence("evidence-3"),),
        ),
    )
    return CanonicalPopulation(
        workspace_id=WORKSPACE,
        generation_id=GENERATION,
        resource="person",
        boundary="all active canonical people",
        records=records,
        candidate_count=4 if not safe else 3,
        unresolved_candidate_ids=("candidate-4",) if not safe else (),
        safely_enumerable=safe,
        ready_projections=("canonical_entities",),
    )


def test_structured_surname_enumeration_is_exhaustive_and_evidence_bound():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    scanned, _ = engine.execute(
        _step("structured", "structured.enumerate", "people"),
        scan,
        population=_population(),
    )
    surname = FilterNode(
        node_id="merters",
        inputs=("people",),
        output_type="entity_set",
        field=FieldReference(resource="person", field="surname"),
        comparator="eq",
        value="Merter",
    )

    filtered, result = engine.execute(
        _step("structured", "structured.filter", "merters"), surname, (scanned,)
    )

    assert [item.values["display_name"] for item in filtered.records] == [
        "Ali Merter",
        "Ayşe Merter",
    ]
    assert result.completeness.state == "complete"
    assert len(result.structured_rows) == len(result.text_evidence) == 2


def test_relation_aggregate_counts_distinct_properties_keeps_zeroes_and_ranks_stably():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    source = _population().model_copy(
        update={
            "records": (
                *_population().records,
                CanonicalRecord(
                    record_id="person-4",
                    resource="person",
                    values={"display_name": "Arda Merter", "surname": "Merter"},
                    evidence=(_evidence("evidence-4"),),
                ),
                CanonicalRecord(
                    record_id="person-5",
                    resource="person",
                    values={"display_name": "Cem Merter", "surname": "Merter"},
                    evidence=(_evidence("evidence-5"),),
                ),
            ),
            "candidate_count": 5,
        }
    )
    scan = ScanNode(
        node_id="people_for_properties",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    scanned, _ = engine.execute(
        _step("structured", "structured.enumerate", scan.node_id), scan, population=source
    )
    filtered, _ = engine.execute(
        _step("structured", "structured.filter", "merters_for_properties"),
        FilterNode(
            node_id="merters_for_properties",
            inputs=(scan.node_id,),
            output_type="entity_set",
            field=FieldReference(resource="person", field="surname"),
            comparator="eq",
            value="Merter",
        ),
        (scanned,),
    )
    aggregate = RelationAggregateNode(
        node_id="property_counts",
        inputs=("merters_for_properties",),
        relation=RelationReference(
            relation="owns", source_resource="person", target_resource="asset_property"
        ),
        target_identity_field=FieldReference(resource="asset_property", field="entity_id"),
    )
    ranked, result = engine.execute(
        _step("structured", "structured.relation_aggregate", aggregate.node_id),
        aggregate,
        (filtered,),
        relation_targets={
            "person-1": (
                ("property-1", (_evidence("ownership-1"),)),
                ("property-1", (_evidence("ownership-2"),)),
                ("property-2", (_evidence("ownership-3"),)),
            ),
            "person-2": (("property-3", (_evidence("ownership-4"),)),),
        },
    )

    assert [
        (item.values["display_name"], item.values["property_count"]) for item in ranked.records
    ] == [
        ("Ali Merter", 2),
        ("Ayşe Merter", 1),
        ("Arda Merter", 0),
        ("Cem Merter", 0),
    ]
    assert [item.values["property_count"] for item in result.structured_rows] == [2, 1, 0, 0]


def test_answer_engine_preserves_every_exhaustive_ranked_structured_row():
    package = ReasoningPackage(
        workspace_id=WORKSPACE,
        generation_id=GENERATION,
        state="corpus_complete",
        structured_rows=tuple(
            GroundedItem(
                item_id=f"person-{ordinal}",
                values={"display_name": f"Person {ordinal}", "property_count": ordinal},
                evidence_ids=(f"evidence-{ordinal}",),
            )
            for ordinal in range(1, 5)
        ),
        completeness=CompletenessReport(
            coverage="exhaustive",
            state="complete",
            boundary="all governed people",
            generation_id=GENERATION,
            candidate_count=4,
            processed_count=4,
            confirmed_count=4,
        ),
        confidence=1.0,
    )

    answer = AnswerEngine().render(package)

    assert answer.metadata["answer_engine"] == "query_v2"
    assert all(f"Person {ordinal}" in answer.content for ordinal in range(1, 5))


def test_structured_count_group_rank_min_max_and_projection_are_generic():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    value, _ = engine.execute(
        _step("structured", "structured.enumerate", "people"),
        scan,
        population=_population(),
    )
    count = CountNode(node_id="count", inputs=("people",), output_type="scalar")
    counted, count_result = engine.execute(
        _step("structured", "structured.count", "count"), count, (value,)
    )
    assert counted.scalar == 3
    assert count_result.aggregates[0].value == 3

    group = GroupNode(
        node_id="by_surname",
        inputs=("people",),
        keys=(FieldReference(resource="person", field="surname"),),
    )
    grouped, group_result = engine.execute(
        _step("structured", "structured.group", "by_surname"), group, (value,)
    )
    assert sorted(item.values["confirmed_count"] for item in group_result.structured_rows) == [1, 2]

    minimum = AggregateNode(
        node_id="minimum",
        inputs=("people",),
        output_type="scalar",
        function="minimum",
        field=FieldReference(resource="person", field="score"),
        alias="minimum_score",
    )
    _, minimum_result = engine.execute(
        _step("structured", "structured.aggregate", "minimum"), minimum, (value,)
    )
    assert minimum_result.aggregates[0].value == 4

    rank = RankNode(
        node_id="top_two",
        inputs=("people",),
        by=FieldReference(resource="person", field="score"),
        direction="descending",
        top_n=2,
    )
    ranked, _ = engine.execute(_step("structured", "structured.rank", "top_two"), rank, (value,))
    assert [item.values["score"] for item in ranked.records] == [12, 8]

    project = ProjectNode(
        node_id="names",
        inputs=("people",),
        fields=(
            ProjectionField(
                name="name",
                source_node_id="people",
                source_field=FieldReference(resource="person", field="display_name"),
            ),
        ),
    )
    projected, _ = engine.execute(
        _step("structured", "structured.project", "names"), project, (value,)
    )
    assert projected.records[0].values == {"name": "Ali Merter"}
    assert len(grouped.groups) == 2


def test_structured_distinct_maximum_and_population_comparison_are_exact():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    value, _ = engine.execute(
        _step("structured", "structured.enumerate", "people"),
        scan,
        population=_population(),
    )
    distinct = DistinctNode(
        node_id="surnames",
        inputs=("people",),
        output_type="entity_set",
        fields=(FieldReference(resource="person", field="surname"),),
    )
    distinct_value, _ = engine.execute(
        _step("structured", "structured.distinct", "surnames"), distinct, (value,)
    )
    assert len(distinct_value.records) == 2

    maximum = AggregateNode(
        node_id="maximum",
        inputs=("people",),
        output_type="scalar",
        function="maximum",
        field=FieldReference(resource="person", field="score"),
        alias="maximum_score",
    )
    _, maximum_result = engine.execute(
        _step("structured", "structured.aggregate", "maximum"), maximum, (value,)
    )
    assert maximum_result.aggregates[0].value == 12

    compare = CompareNode(
        node_id="comparison", inputs=("people", "surnames"), comparison="populations"
    )
    compared, _ = engine.execute(
        _step("structured", "structured.compare", "comparison"),
        compare,
        (value, distinct_value),
    )
    assert compared.scalar == {"left": 3, "right": 2}


def test_unsafe_enumeration_reports_confirmed_and_unresolved_without_approximation():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )

    _, result = engine.execute(
        _step("structured", "structured.enumerate", "people"),
        scan,
        population=_population(safe=False),
    )

    assert result.state == "partial"
    assert result.completeness.confirmed_count == 3
    assert result.completeness.unresolved_candidate_ids == ("candidate-4",)
    assert result.failures[0].reason == "canonical population is not safely enumerable"


def test_structured_population_adapter_preserves_bounded_truncation():
    class Reader:
        workspace_id = WORKSPACE

        def query_canonical_population(self, generation, resource, *, safe_limit=500):
            return CanonicalPopulationQueryView(
                WORKSPACE,
                GENERATION,
                resource,
                (
                    CanonicalEntityQueryView(
                        "entity-1", "person", "Ali Merter", None, (_graph_evidence(),)
                    ),
                ),
                501,
                False,
            )

    population = load_canonical_population(Reader(), GENERATION, "person")

    assert population.candidate_count == 501
    assert population.safely_enumerable is False
    assert population.unresolved_candidate_ids == ("population-beyond-safe-limit",)


def test_structured_engine_rejects_workspace_or_generation_mismatch():
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
    )
    wrong = _step("structured", "structured.enumerate", "people").model_copy(
        update={
            "readiness": ReadinessRequirement(workspace_id="workspace-2", generation_id=GENERATION)
        }
    )
    with pytest.raises(ValueError, match="workspace"):
        engine.execute(wrong, scan, population=_population())


def _graph_evidence(evidence_id: str = "graph-evidence") -> CanonicalEvidenceQueryView:
    return CanonicalEvidenceQueryView(
        evidence_id=evidence_id,
        document_id="document-graph",
        document_version_id="version-graph",
        logical_document_id="logical-graph",
        chunk_id="chunk-graph",
        start_offset=0,
        end_offset=7,
        source_text="owns 42",
        confidence=0.9,
        generation=GENERATION,
    )


@dataclass
class FakeGraphReader:
    workspace_id: str = WORKSPACE
    unresolved: bool = False
    canonical_event_rows: tuple[CanonicalEventQueryView, ...] = ()
    canonical_event_calls: list[tuple[str, str]] = field(default_factory=list)
    event_path_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def query_canonical_entities(self, generation, entity_ids):
        if self.unresolved:
            return ()
        return tuple(
            CanonicalEntityQueryView(
                entity_id, "person", f"Person {index}", None, (_graph_evidence(),)
            )
            for index, entity_id in enumerate(entity_ids)
        )

    def query_canonical_paths(
        self,
        generation,
        start_entity_ids,
        relation_type,
        direction,
        minimum_hops,
        maximum_hops,
        *,
        limit=500,
    ):
        return (
            CanonicalPathQueryView(
                "path-1",
                (start_entity_ids[0], "entity-2", "entity-3"),
                ("relation-1", "relation-2"),
                (relation_type, relation_type),
                (_graph_evidence(),),
            ),
        )

    def query_event_paths(
        self, generation, entity_ids, *, normalized_start=None, normalized_end=None, limit=500
    ):
        self.event_path_calls.append((generation, entity_ids))
        return (
            CanonicalPathQueryView(
                "event-path",
                (entity_ids[0], "event-1"),
                ("participation-1",),
                ("event_participation:owner",),
                (_graph_evidence(),),
            ),
        )

    def query_canonical_events(self, generation, *, event_date, limit=500):
        self.canonical_event_calls.append((generation, event_date))
        return self.canonical_event_rows

    def query_claim_conflicts(self, generation, subject_ids, *, limit=500):
        return (
            CanonicalConflictQueryView(
                "claim-1",
                "claim-2",
                subject_ids[0],
                "registered_city",
                "Ankara",
                "İzmir",
                "different supported values",
                (_graph_evidence(),),
            ),
        )

    def query_canonical_artifact_evidence(self, generation, artifact_ids, *, limit=500):
        return (_graph_evidence(),)


def _resolve(candidate: bool = False) -> ResolveNode:
    return ResolveNode(
        node_id="resolve",
        workspace_id=WORKSPACE,
        resource="person",
        reference_id="person_ref",
        mention="Merter",
        canonical_entity_ids=() if candidate else ("entity-1",),
        candidate_entity_ids=("entity-1", "entity-2") if candidate else (),
    )


def test_graph_engine_resolves_and_executes_evidence_bound_multi_hop():
    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, FakeGraphReader())
    resolved, entity_result = engine.execute(
        _step("knowledge_graph", "graph.entity_resolve", "resolve"), _resolve()
    )
    traverse = TraverseNode(
        node_id="traverse",
        inputs=("resolve",),
        output_type="graph_paths",
        relation=RelationReference(
            relation="owns", source_resource="person", target_resource="asset_property"
        ),
        maximum_hops=3,
    )
    traversed, path_result = engine.execute(
        _step("knowledge_graph", "graph.multi_hop", "traverse"),
        traverse,
        (resolved,),
    )

    assert entity_result.entities[0].entity_id == "entity-1"
    assert traversed.entity_ids == ("entity-3",)
    assert path_result.graph_paths[0].relation_ids == ("relation-1", "relation-2")
    assert path_result.text_evidence[0].source_text == "owns 42"

    provenance = CustomCapabilityNode(
        node_id="provenance",
        inputs=("traverse",),
        capability="graph.provenance_traversal",
    )
    _, provenance_result = engine.execute(
        _step("knowledge_graph", "graph.provenance_traversal", "provenance"),
        provenance,
        (traversed,),
    )
    assert provenance_result.graph_paths[0].evidence_ids == ("graph-evidence",)


def test_graph_temporal_event_and_conflict_inspection_preserve_evidence():
    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, FakeGraphReader())
    value = GraphValue(entity_ids=("entity-1",))
    temporal = TemporalConstraintNode(
        node_id="temporal",
        inputs=("resolve",),
        output_type="entity_set",
        predicates=(
            TemporalPredicate(
                role="range",
                original_text="in 1988",
                normalized_start="1988-01-01",
                normalized_end="1988-12-31",
                precision="year",
                uncertainty="certain",
            ),
        ),
    )
    _, temporal_result = engine.execute(
        _step("knowledge_graph", "graph.temporal_reasoning", "temporal"),
        temporal,
        (value,),
    )
    conflict = CustomCapabilityNode(
        node_id="conflicts", inputs=("resolve",), capability="graph.contradiction_analysis"
    )
    _, conflict_result = engine.execute(
        _step("knowledge_graph", "graph.contradiction_analysis", "conflicts"),
        conflict,
        (value,),
    )

    assert temporal_result.graph_paths[0].node_ids[-1] == "event-1"
    assert len(conflict_result.claims) == 2
    assert conflict_result.conflicts[0].left_result_id == "claim-1"
    assert conflict_result.text_evidence


def _event_filter(date_value: str | None = "1974-06-12") -> TemporalConstraintNode:
    return TemporalConstraintNode(
        node_id="event_filter",
        inputs=("event_population",),
        output_type="event_set",
        predicates=(
            TemporalPredicate(
                role="event_date",
                original_text="12 June 1974",
                normalized_start=date_value,
                normalized_end=date_value,
                precision="day",
                uncertainty="certain",
            ),
        ),
    )


def test_graph_event_filter_executes_unanchored_exact_date_and_preserves_events():
    event = CanonicalEventQueryView(
        "E1",
        "generic_event",
        "Event One",
        "1974-06-12",
        ("P1", "P2"),
        (_graph_evidence("event-evidence"),),
    )
    reader = FakeGraphReader(canonical_event_rows=(event,))
    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, reader)

    value, result = engine.execute(
        _step("knowledge_graph", "graph.event_filter", "event_filter"),
        _event_filter(),
    )

    assert reader.canonical_event_calls == [(GENERATION, "1974-06-12")]
    assert reader.event_path_calls == []
    assert value.events == (event,)
    assert result.events[0].event_id == "E1"
    assert result.events[0].event_type == "generic_event"
    assert result.events[0].event_name == "Event One"
    assert result.events[0].event_date == "1974-06-12"
    assert result.events[0].participant_canonical_ids == ("P1", "P2")
    assert result.text_evidence[0].evidence_id == "event-evidence"
    assert result.workspace_id == WORKSPACE
    assert result.generation_id == GENERATION


@pytest.mark.parametrize("event_date", [None, "1974-99-12"])
def test_graph_event_filter_rejects_missing_or_invalid_exact_date(event_date):
    reader = FakeGraphReader()
    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, reader)

    with pytest.raises(GraphExecutionError, match="exact event_date ISO day"):
        engine.execute(
            _step("knowledge_graph", "graph.event_filter", "event_filter"),
            _event_filter(event_date),
        )

    assert reader.canonical_event_calls == []
    assert reader.event_path_calls == []


def test_graph_unresolved_and_ambiguous_entities_are_explicit():
    unresolved_engine = KnowledgeGraphEngine(
        WORKSPACE, GENERATION, FakeGraphReader(unresolved=True)
    )
    _, unresolved = unresolved_engine.execute(
        _step("knowledge_graph", "graph.entity_resolve", "resolve"), _resolve()
    )
    assert unresolved.state == "unsupported"

    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, FakeGraphReader())
    _, ambiguous = engine.execute(
        _step("knowledge_graph", "graph.entity_resolve", "resolve"), _resolve(candidate=True)
    )
    assert ambiguous.state == "ambiguous"
    assert ambiguous.ambiguities[0].candidate_ids == ("entity-1", "entity-2")


def test_graph_engine_rejects_non_adapter_workspace_and_wrong_step():
    with pytest.raises(ValueError, match="workspace"):
        KnowledgeGraphEngine(WORKSPACE, GENERATION, FakeGraphReader("workspace-2"))
    engine = KnowledgeGraphEngine(WORKSPACE, GENERATION, FakeGraphReader())
    with pytest.raises(GraphExecutionError, match="physical step"):
        engine.execute(_step("structured", "structured.filter", "resolve"), _resolve())


class _Consumed:
    def consume(self):
        return None


class _Transaction:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return _Consumed()


class _Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute_write(self, callback, **kwargs):
        transaction = _Transaction()
        self.driver.transactions.append(transaction.calls)
        return callback(transaction, **kwargs)


class _Driver:
    def __init__(self, query_results=()):
        self.query_results = list(query_results)
        self.query_calls = []
        self.transactions = []

    def execute_query(self, query, **parameters):
        self.query_calls.append((query, parameters))
        records = self.query_results.pop(0) if self.query_results else []
        return records, None, None

    def session(self, **parameters):
        return _Session(self)

    def close(self):
        return None


def _provenance() -> ExactSourceProvenance:
    return ExactSourceProvenance(
        workspace_id=WORKSPACE,
        document_id="document-1",
        document_version_id="version-1",
        logical_document_id="logical-1",
        chunk_id="chunk-1",
        start_offset=0,
        end_offset=7,
        source_text="owns 42",
        extraction_run_id="run-1",
        provider="provider",
        model="model",
        prompt_version="prompt-1",
        schema_version="schema-1",
        confidence=0.9,
        validation_state="passed",
        generation=GENERATION,
    )


def test_neo4j_adapter_materializes_canonical_edges_with_exact_lineage():
    driver = _Driver()
    adapter = Neo4jGraphAdapter(WORKSPACE, driver)
    relation = CanonicalRelation(
        relation_id=str(uuid4()),
        source_entity_id=str(uuid4()),
        target_entity_id=str(uuid4()),
        relation_type="owns",
        authority=KnowledgeAuthority.VALIDATED,
        generation=GENERATION,
        support=RelationSupport.EXACT_SPAN,
        evidence=(_provenance(),),
        properties={},
    )

    adapter.upsert_relation(relation)

    calls = driver.transactions[0]
    assert "HAS_LOGICAL_DOCUMENT" in calls[0][0]
    assert calls[0][1]["evidence"][0]["source_text"] == "owns 42"
    assert "CORTEX_CANONICAL_RELATION" in calls[1][0]
    assert calls[1][1]["workspace_id"] == WORKSPACE
    assert calls[1][1]["generation"] == GENERATION


def test_neo4j_traversal_query_is_workspace_generation_and_hop_bounded():
    source_id, target_id, relation_id = str(uuid4()), str(uuid4()), str(uuid4())
    driver = _Driver(
        (
            [
                {
                    "node_ids": [source_id, target_id],
                    "relation_ids": [relation_id],
                    "relation_types": ["owns"],
                }
            ],
            [],
        )
    )
    adapter = Neo4jGraphAdapter(WORKSPACE, driver)

    paths = adapter.query_canonical_paths(GENERATION, (source_id,), "owns", "outgoing", 1, 3)

    query, parameters = driver.query_calls[0]
    assert "CORTEX_CANONICAL_RELATION*1..3" in query
    assert "rel.workspace_id = $workspace_id" in query
    assert "rel.generation = $generation" in query
    assert parameters["workspace_id"] == WORKSPACE
    assert parameters["generation"] == GENERATION
    assert paths[0].node_ids == (source_id, target_id)


def test_neo4j_population_reader_counts_before_bounded_enumeration():
    entity_id = str(uuid4())
    driver = _Driver(
        (
            [{"candidate_count": 1}],
            [{"entity_id": entity_id}],
            [
                {
                    "entity_id": entity_id,
                    "entity_type": "person",
                    "display_name": "Ali Merter",
                    "subtype": None,
                }
            ],
            [],
        )
    )
    adapter = Neo4jGraphAdapter(WORKSPACE, driver)

    population = adapter.query_canonical_population(GENERATION, "person", safe_limit=10)

    assert population.candidate_count == 1
    assert population.safely_enumerable is True
    assert population.entities[0].entity_id == entity_id
    assert driver.query_calls[0][1]["workspace_id"] == WORKSPACE
    assert driver.query_calls[0][1]["generation"] == GENERATION
    assert driver.query_calls[1][1]["limit"] == 10


def test_exhaustive_zero_count_retains_population_evidence():
    """A governed zero is a completed structured result, not an engine failure."""
    engine = StructuredQueryEngine(WORKSPACE, GENERATION)
    scan = ScanNode(
        node_id="people",
        workspace_id=WORKSPACE,
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    scanned, _ = engine.execute(
        _step("structured", "structured.enumerate", "people"),
        scan,
        population=_population(),
    )
    filtered, _ = engine.execute(
        _step("structured", "structured.filter", "no-demir"),
        FilterNode(
            node_id="no-demir",
            inputs=("people",),
            output_type="entity_set",
            field=FieldReference(resource="person", field="surname"),
            comparator="eq",
            value="Demir",
        ),
        (scanned,),
    )
    _, result = engine.execute(
        _step("structured", "structured.count", "count-zero"),
        CountNode(node_id="count-zero", inputs=("no-demir",), output_type="scalar"),
        (filtered,),
    )

    assert result.state == "success"
    assert result.completeness.state == "complete"
    assert result.aggregates[0].value == 0
    assert result.text_evidence
