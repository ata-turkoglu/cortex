import json

import pytest
from pydantic import ValidationError

from app.query.ir import (
    AggregateNode,
    CompareNode,
    CountNode,
    CoverageContract,
    CustomCapabilityNode,
    DistinctNode,
    EventSetNode,
    EvidenceRequirement,
    ExistsNode,
    FieldReference,
    FilterNode,
    GroupNode,
    IRValidationError,
    IRVocabulary,
    JoinNode,
    LimitNode,
    LogicalQueryIR,
    OutputProjection,
    ProjectionField,
    ProjectNode,
    RankNode,
    RelationAggregateNode,
    RelationDeclaration,
    ResolveNode,
    ScanNode,
    SortKey,
    SortNode,
    SummarizeNode,
    TemporalConstraintNode,
    TemporalPredicate,
    TraverseNode,
    lower_semantic_understanding,
    parse_logical_ir,
    validate_logical_ir,
)
from app.query.understanding import (
    InterpretationCandidate,
    SemanticEntity,
    SemanticRelation,
    SemanticRelationAggregate,
    SemanticTarget,
    SemanticTemporalConstraint,
    SemanticTypedFilter,
    SemanticUnderstanding,
)


def _coverage() -> CoverageContract:
    return CoverageContract(
        mode="exhaustive",
        population_boundary="all active workspace property records",
        same_generation_required=True,
        partial_results_allowed=False,
    )


def _property_scan(node_id: str = "scan_properties") -> ScanNode:
    return ScanNode(
        node_id=node_id,
        output_type="entity_set",
        workspace_id="workspace-1",
        resource="asset_property",
        population_mode="exhaustive",
    )


def _ir(nodes, root_id: str, shape: str) -> LogicalQueryIR:
    return LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=tuple(nodes),
        root_ids=(root_id,),
        output=OutputProjection(shape=shape),
        coverage=_coverage(),
    )


def test_ir_schema_is_versioned_has_all_operator_families_and_no_intent():
    schema_text = json.dumps(LogicalQueryIR.model_json_schema()).casefold()
    for operator in (
        "scan",
        "event_set",
        "resolve",
        "filter",
        "traverse",
        "join",
        "distinct",
        "group",
        "aggregate",
        "count",
        "rank",
        "sort",
        "limit",
        "project",
        "temporal_constraint",
        "retrieve_evidence",
        "compare",
        "exists",
        "summarize",
        "custom_capability",
    ):
        assert f'"{operator}"' in schema_text
    assert '"intent"' not in schema_text
    assert '"1.0"' in schema_text


def test_event_population_accepts_only_exact_governed_event_dates():
    events = EventSetNode(node_id="events")
    exact = TemporalConstraintNode(
        node_id="events_on_date",
        inputs=(events.node_id,),
        output_type="event_set",
        predicates=(
            {
                "role": "event_date", "original_text": "12.06.1974",
                "normalized_start": "1974-06-12", "normalized_end": "1974-06-12",
                "precision": "day", "uncertainty": "certain",
            },
        ),
    )
    ir = LogicalQueryIR(
        workspace_id="workspace-1", state="resolved", nodes=(events, exact),
        root_ids=(exact.node_id,), output=OutputProjection(shape="rows"),
        coverage=CoverageContract(mode="grounded"),
    )
    validate_logical_ir(ir, IRVocabulary.core())
    for payload in (
        {**exact.predicates[0].model_dump(), "role": "document_date"},
        {
            **exact.predicates[0].model_dump(),
            "normalized_start": "1974-02-31",
            "normalized_end": "1974-02-31",
        },
    ):
        invalid = ir.model_copy(
            update={
                "nodes": (
                    events,
                    exact.model_copy(
                        update={"predicates": (TemporalPredicate.model_validate(payload),)}
                    ),
                )
            }
        )
        with pytest.raises(IRValidationError, match="event_date ISO day|calendar date"):
            validate_logical_ir(invalid, IRVocabulary.core())


@pytest.mark.parametrize(
    ("tail", "shape"),
    [
        (
            CountNode(
                node_id="count_properties",
                inputs=("scan_properties",),
                output_type="scalar",
                distinct_fields=(
                    FieldReference(resource="asset_property", field="entity_id"),
                ),
            ),
            "scalar",
        ),
        (
            AggregateNode(
                node_id="minimum_parcel",
                inputs=("scan_properties",),
                output_type="scalar",
                function="minimum",
                field=FieldReference(resource="asset_property", field="parcel"),
                alias="minimum_parcel",
            ),
            "scalar",
        ),
        (
            AggregateNode(
                node_id="maximum_parcel",
                inputs=("scan_properties",),
                output_type="scalar",
                function="maximum",
                field=FieldReference(resource="asset_property", field="parcel"),
                alias="maximum_parcel",
            ),
            "scalar",
        ),
        (
            RankNode(
                node_id="top_properties",
                inputs=("scan_properties",),
                by=FieldReference(resource="asset_property", field="parcel"),
                direction="descending",
                top_n=10,
            ),
            "rows",
        ),
    ],
)
def test_ir_represents_count_min_max_rank_and_top_n(tail, shape):
    ir = _ir([_property_scan(), tail], tail.node_id, shape)
    assert validate_logical_ir(ir, IRVocabulary.core()) is ir


def test_ir_represents_list_distinct_group_and_population_comparison():
    scan = _property_scan()
    distinct = DistinctNode(
        node_id="distinct_properties",
        inputs=(scan.node_id,),
        output_type="entity_set",
        fields=(FieldReference(resource="asset_property", field="entity_id"),),
    )
    project = ProjectNode(
        node_id="list_properties",
        inputs=(distinct.node_id,),
        fields=(
            ProjectionField(
                name="parcel",
                source_node_id=distinct.node_id,
                source_field=FieldReference(resource="asset_property", field="parcel"),
            ),
        ),
    )
    listing = _ir([scan, distinct, project], project.node_id, "rows")
    validate_logical_ir(listing, IRVocabulary.core())

    group = GroupNode(
        node_id="group_by_district",
        inputs=(scan.node_id,),
        keys=(FieldReference(resource="asset_property", field="district"),),
    )
    grouped_count = CountNode(
        node_id="count_by_district",
        inputs=(group.node_id,),
        output_type="record_set",
    )
    grouped = _ir([scan, group, grouped_count], grouped_count.node_id, "rows")
    validate_logical_ir(grouped, IRVocabulary.core())

    other_scan = _property_scan("scan_other_properties")
    compare = CompareNode(
        node_id="compare_populations",
        inputs=(scan.node_id, other_scan.node_id),
        comparison="populations",
    )
    comparison = _ir([scan, other_scan, compare], compare.node_id, "comparison")
    validate_logical_ir(comparison, IRVocabulary.core())


def test_ir_rejects_cycles_unknown_inputs_and_incompatible_types():
    payload = {
        "workspace_id": "workspace-1",
        "state": "resolved",
        "nodes": [
            {
                "kind": "filter",
                "node_id": "filter_a",
                "inputs": ["filter_b"],
                "output_type": "entity_set",
                "field": {"resource": "person", "field": "status"},
                "comparator": "eq",
                "value": "active",
            },
            {
                "kind": "filter",
                "node_id": "filter_b",
                "inputs": ["filter_a"],
                "output_type": "entity_set",
                "field": {"resource": "person", "field": "status"},
                "comparator": "eq",
                "value": "active",
            },
        ],
        "root_ids": ["filter_a"],
        "output": {"shape": "entities"},
        "coverage": {"mode": "grounded"},
        "evidence": {},
    }
    with pytest.raises(ValidationError, match="acyclic"):
        LogicalQueryIR.model_validate(payload)

    payload["nodes"][0]["inputs"] = ["missing"]
    payload["nodes"] = payload["nodes"][:1]
    with pytest.raises(ValidationError, match="unknown input"):
        LogicalQueryIR.model_validate(payload)

    scan = _property_scan()
    mismatched = DistinctNode(
        node_id="distinct",
        inputs=(scan.node_id,),
        output_type="record_set",
    )
    with pytest.raises(IRValidationError, match="preserve"):
        validate_logical_ir(
            _ir([scan, mismatched], mismatched.node_id, "rows"), IRVocabulary.core()
        )


def test_ir_rejects_cross_workspace_unknown_fields_relations_and_extensions():
    scan = _property_scan()
    payload = scan.model_dump(mode="json") | {"workspace_id": "workspace-2"}
    foreign_scan = ScanNode.model_validate(payload)
    with pytest.raises(IRValidationError, match="workspace"):
        validate_logical_ir(
            _ir([foreign_scan], foreign_scan.node_id, "entities"), IRVocabulary.core()
        )

    invalid_count = CountNode(
        node_id="count",
        inputs=(scan.node_id,),
        output_type="scalar",
        distinct_fields=(FieldReference(resource="asset_property", field="invented"),),
    )
    with pytest.raises(IRValidationError, match="field"):
        validate_logical_ir(_ir([scan, invalid_count], "count", "scalar"), IRVocabulary.core())

    person = ResolveNode(
        node_id="person",
        workspace_id="workspace-1",
        reference_id="person_ref",
        resource="person",
        mention="Hasan",
        canonical_entity_ids=("person-1",),
    )
    invented_relation = TraverseNode(
        node_id="invented_relation",
        inputs=(person.node_id,),
        output_type="entity_set",
        relation={
            "relation": "invented_relation",
            "source_resource": "person",
            "target_resource": "entity",
        },
    )
    relation_ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(person, invented_relation),
        root_ids=(invented_relation.node_id,),
        output=OutputProjection(shape="entities"),
        coverage=CoverageContract(mode="grounded"),
    )
    with pytest.raises(IRValidationError, match="relation"):
        validate_logical_ir(relation_ir, IRVocabulary.core())

    custom = CustomCapabilityNode(node_id="custom", capability="family_matrix")
    custom_ir = _ir([custom], "custom", "rows")
    with pytest.raises(IRValidationError, match="custom capability"):
        validate_logical_ir(custom_ir, IRVocabulary.core())


def test_filter_join_sort_limit_exists_and_declared_extension_validate():
    person_scan = ScanNode(
        node_id="people",
        output_type="entity_set",
        workspace_id="workspace-1",
        resource="person",
    )
    active = FilterNode(
        node_id="active_people",
        inputs=(person_scan.node_id,),
        output_type="entity_set",
        field=FieldReference(resource="person", field="status"),
        comparator="eq",
        value="active",
    )
    ordered = SortNode(
        node_id="ordered_people",
        inputs=(active.node_id,),
        output_type="entity_set",
        keys=(SortKey(field=FieldReference(resource="person", field="display_name")),),
    )
    limited = LimitNode(
        node_id="limited_people",
        inputs=(ordered.node_id,),
        output_type="entity_set",
        limit=10,
    )
    exists = ExistsNode(node_id="people_exist", inputs=(limited.node_id,))
    existence_ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(person_scan, active, ordered, limited, exists),
        root_ids=(exists.node_id,),
        output=OutputProjection(shape="boolean"),
        coverage=CoverageContract(mode="grounded"),
    )
    validate_logical_ir(existence_ir, IRVocabulary.core())

    organization_scan = ScanNode(
        node_id="organizations",
        output_type="entity_set",
        workspace_id="workspace-1",
        resource="organization",
    )
    joined = JoinNode(
        node_id="people_organizations",
        inputs=(person_scan.node_id, organization_scan.node_id),
        conditions=(
            {
                "left": {"resource": "person", "field": "entity_id"},
                "right": {"resource": "organization", "field": "entity_id"},
            },
        ),
    )
    projected = ProjectNode(
        node_id="joined_names",
        inputs=(joined.node_id,),
        fields=(
            ProjectionField(
                name="person_name",
                source_node_id=joined.node_id,
                source_field=FieldReference(resource="person", field="display_name"),
            ),
        ),
    )
    join_ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(person_scan, organization_scan, joined, projected),
        root_ids=(projected.node_id,),
        output=OutputProjection(shape="rows"),
        coverage=CoverageContract(mode="grounded"),
    )
    validate_logical_ir(join_ir, IRVocabulary.core())

    custom = CustomCapabilityNode(node_id="custom", capability="family_matrix")
    summarize = SummarizeNode(node_id="summarize_custom", inputs=(custom.node_id,))
    custom_ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(custom, summarize),
        root_ids=(summarize.node_id,),
        output=OutputProjection(shape="summary"),
        coverage=CoverageContract(mode="grounded"),
    )
    vocabulary = IRVocabulary(
        resources=IRVocabulary.core().resources,
        custom_capabilities=frozenset({"family_matrix"}),
    )
    validate_logical_ir(custom_ir, vocabulary)


def test_projection_cannot_read_from_an_unrelated_branch():
    people = ScanNode(
        node_id="people",
        output_type="entity_set",
        workspace_id="workspace-1",
        resource="person",
    )
    organizations = ScanNode(
        node_id="organizations",
        output_type="entity_set",
        workspace_id="workspace-1",
        resource="organization",
    )
    projected = ProjectNode(
        node_id="project_people",
        inputs=(people.node_id,),
        fields=(
            ProjectionField(
                name="organization_name",
                source_node_id=organizations.node_id,
                source_field=FieldReference(resource="organization", field="display_name"),
            ),
        ),
    )
    joined_root = JoinNode(
        node_id="retain_branches",
        inputs=(projected.node_id, organizations.node_id),
        conditions=(
            {
                "left": {"resource": "person", "field": "entity_id"},
                "right": {"resource": "organization", "field": "entity_id"},
            },
        ),
    )
    ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(people, organizations, projected, joined_root),
        root_ids=(joined_root.node_id,),
        output=OutputProjection(shape="rows"),
        coverage=CoverageContract(mode="grounded"),
    )
    with pytest.raises(IRValidationError, match="not upstream"):
        validate_logical_ir(ir, IRVocabulary.core())


def test_aggregation_rejects_grounded_top_k_coverage_and_weak_evidence():
    scan = _property_scan().model_copy(update={"population_mode": "discovery"})
    count = CountNode(
        node_id="count",
        inputs=(scan.node_id,),
        output_type="scalar",
    )
    ir = LogicalQueryIR(
        workspace_id="workspace-1",
        state="resolved",
        nodes=(scan, count),
        root_ids=(count.node_id,),
        output=OutputProjection(shape="scalar"),
        coverage=CoverageContract(mode="grounded"),
    )
    with pytest.raises(IRValidationError, match="exhaustive"):
        validate_logical_ir(ir, IRVocabulary.core())

    weak = _ir([_property_scan(), count], count.node_id, "scalar").model_copy(
        update={
            "evidence": EvidenceRequirement(
                citation_granularity="source", provenance_chain_required=False
            )
        }
    )
    with pytest.raises(IRValidationError, match="provenance"):
        validate_logical_ir(weak, IRVocabulary.core())


def test_safe_repair_only_removes_duplicate_graph_references():
    payload = {
        "workspace_id": "workspace-1",
        "state": "resolved",
        "nodes": [
            _property_scan().model_dump(mode="json"),
            {
                "kind": "distinct",
                "node_id": "distinct",
                "inputs": ["scan_properties", "scan_properties"],
                "output_type": "entity_set",
                "fields": [],
            },
        ],
        "root_ids": ["distinct", "distinct"],
        "output": {"shape": "entities", "fields": []},
        "coverage": _coverage().model_dump(mode="json"),
        "evidence": {},
        "candidate_plans": [],
        "issues": [],
    }
    repaired = parse_logical_ir(payload, IRVocabulary.core())
    assert repaired.schema_version == "1.0"
    assert repaired.root_ids == ("distinct",)
    assert repaired.nodes[-1].inputs == ("scan_properties",)

    payload["nodes"][0]["resource"] = "invented"
    with pytest.raises(IRValidationError, match="resource"):
        parse_logical_ir(payload, IRVocabulary.core())


def test_semantic_relation_and_temporal_meaning_lower_to_typed_dag():
    understanding = SemanticUnderstanding(
        state="resolved",
        entities=(
            SemanticEntity(
                reference_id="parent",
                mention="Hasan Tahsin Merter",
                entity_type="person",
                resolution="resolved",
                canonical_entity_id="person-1",
            ),
        ),
        targets=(
            SemanticTarget(
                target_type="entity", reference_id="parent", description="the named person"
            ),
        ),
        relations=(
            SemanticRelation(predicate="children_of", subject_reference_id="parent"),
        ),
        temporal_constraints=(
            SemanticTemporalConstraint(
                role="mentioned_date",
                original_text="in 1988",
                normalized_start="1988",
                precision="year",
                uncertainty="certain",
            ),
        ),
        operators=("resolve_reference", "traverse_relation", "retrieve_evidence", "summarize"),
        coverage="relevant_evidence",
        confidence=0.95,
    )
    ir = lower_semantic_understanding(understanding, "workspace-1")
    vocabulary = IRVocabulary(
        resources=IRVocabulary.core().resources,
        relations={
            "children_of": RelationDeclaration(
                source_resources=frozenset({"person"}),
                target_resources=frozenset({"entity"}),
            )
        },
    )

    assert ir.state == "resolved"
    assert [node.kind for node in ir.nodes] == [
        "resolve",
        "traverse",
        "temporal_constraint",
        "retrieve_evidence",
        "summarize",
    ]
    assert validate_logical_ir(ir, vocabulary) is ir


def test_governed_person_property_relation_aggregate_lowers_to_one_exact_ranked_root():
    understanding = SemanticUnderstanding(
        state="resolved",
        typed_filters=(
            {
                "target_type": "person",
                "property": "surname",
                "operator": "eq",
                "value": "Merter",
            },
        ),
        structured_operation="rank",
        relation_aggregate=SemanticRelationAggregate(
            source_type="person",
            relation="owns",
            target_type="asset_property",
            direction="descending",
        ),
        # A semantic provider can add a presentation-only summarize hint to
        # this typed ranking.  Lowering must preserve the executable governed
        # aggregate instead of requiring an unrelated summary capability.
        operators=("filter", "enumerate", "aggregate", "order", "summarize"),
        coverage="corpus_required",
        confidence=1.0,
    )

    ir = lower_semantic_understanding(understanding, "workspace-1")

    assert [node.kind for node in ir.nodes] == ["scan", "filter", "relation_aggregate"]
    aggregate = ir.nodes[-1]
    assert isinstance(aggregate, RelationAggregateNode)
    assert aggregate.relation.relation == "owns"
    assert aggregate.target_identity_field.field == "entity_id"
    assert aggregate.direction == "descending"
    assert ir.root_ids == (aggregate.node_id,)
    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    assert validate_logical_ir(ir, vocabulary) is ir


@pytest.mark.parametrize("operation", ("list", "count"))
def test_governed_person_list_and_count_ignore_explanatory_entity_target(operation):
    """A generic Person target plus a governed surname filter is one population."""
    understanding = SemanticUnderstanding(
        state="resolved",
        targets=(SemanticTarget(target_type="entity", description="Persons with surname Merter"),),
        typed_filters=(
            SemanticTypedFilter(
                target_type="person", property="surname", operator="eq", value="Merter"
            ),
        ),
        structured_operation=operation,
        operators=(
            ("filter", "enumerate", "aggregate")
            if operation == "count"
            else ("filter", "enumerate")
        ),
        coverage="corpus_required",
        confidence=1.0,
    )

    ir = lower_semantic_understanding(understanding, "workspace-1")

    assert ir.state == "resolved"
    assert [node.kind for node in ir.nodes] == (
        ["scan", "filter"] if operation == "list" else ["scan", "filter", "count"]
    )
    scan = ir.nodes[0]
    assert isinstance(scan, ScanNode)
    assert scan.resource == "person"
    if operation == "count":
        count = ir.nodes[-1]
        assert isinstance(count, CountNode)
        assert count.distinct_fields == (FieldReference(resource="person", field="entity_id"),)
    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    assert validate_logical_ir(ir, vocabulary) is ir


def test_active_corpus_person_list_lowers_to_one_exhaustive_person_scan():
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="person", description="all active people"),),
            structured_operation="list",
            operators=("enumerate",),
            coverage="corpus_required",
            confidence=1.0,
        ),
        "workspace-1",
    )

    assert ir.state == "resolved"
    assert [node.kind for node in ir.nodes] == ["scan"]
    scan = ir.nodes[0]
    assert isinstance(scan, ScanNode)
    assert scan.resource == "person"
    assert scan.population_mode == "exhaustive"


def test_exact_event_target_lowers_to_event_set_and_exact_event_date_constraint():
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="event", description="events"),),
            temporal_constraints=(
                SemanticTemporalConstraint(
                    role="event_date",
                    original_text="12.06.1974",
                    precision="day",
                    uncertainty="certain",
                ),
            ),
            confidence=1.0,
        ),
        "workspace-1",
    )

    assert [node.kind for node in ir.nodes] == ["event_set", "temporal_constraint"]
    temporal = ir.nodes[-1]
    assert temporal.predicates[0].role == "event_date"
    assert temporal.predicates[0].normalized_start == "1974-06-12"


def test_generic_grounded_document_qa_does_not_require_canonical_scan():
    """Ordinary document QA stays available while Canonical Core is partial."""
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            targets=(SemanticTarget(target_type="document", description="uploaded evidence"),),
            operators=("describe", "retrieve_evidence"),
            coverage="relevant_evidence",
            confidence=1.0,
        ),
        "workspace-1",
    )

    assert [node.kind for node in ir.nodes] == ["retrieve_evidence", "summarize"]
    assert ir.nodes[0].inputs == ()
    assert validate_logical_ir(ir, IRVocabulary.core()) is ir


def test_unresolved_named_entity_description_lowers_to_literal_grounded_retrieval():
    """Identity uncertainty must not suppress evidence retrieval for a description."""
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="unresolved",
            entities=(
                SemanticEntity(
                    reference_id="person",
                    mention="Hasan Tahsin Merter",
                    entity_type="person",
                    resolution="unresolved",
                ),
            ),
            targets=(
                SemanticTarget(
                    target_type="entity", reference_id="person", description="named person"
                ),
            ),
            operators=("describe", "retrieve_evidence"),
            coverage="relevant_evidence",
            unresolved_questions=("Which canonical person is meant?",),
            confidence=0.7,
        ),
        "workspace-1",
    )

    assert ir.state == "resolved"
    assert [node.kind for node in ir.nodes] == ["retrieve_evidence", "summarize"]
    assert ir.nodes[0].inputs == ()
    assert validate_logical_ir(ir, IRVocabulary.core()) is ir


def test_unresolved_unstructured_grounded_request_does_not_depend_on_provider_hints():
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="unresolved",
            coverage="relevant_evidence",
            unresolved_questions=("Which canonical person is meant?",),
            confidence=0.5,
        ),
        "workspace-1",
    )

    assert ir.state == "resolved"
    assert [node.kind for node in ir.nodes] == ["retrieve_evidence"]
    assert validate_logical_ir(ir, IRVocabulary.core()) is ir


def test_unresolved_named_entity_canonical_count_stays_non_retrieval():
    ir = lower_semantic_understanding(
        SemanticUnderstanding(
            state="unresolved",
            entities=(
                SemanticEntity(
                    reference_id="person",
                    mention="Hasan Tahsin Merter",
                    entity_type="person",
                    resolution="unresolved",
                ),
            ),
            targets=(
                SemanticTarget(
                    target_type="entity", reference_id="person", description="named person"
                ),
            ),
            operators=("aggregate",),
            structured_operation="count",
            typed_filters=(
                SemanticTypedFilter(
                    target_type="person", property="surname", operator="eq", value="Merter"
                ),
            ),
            coverage="corpus_required",
            unresolved_questions=("Which canonical person is meant?",),
            confidence=0.7,
        ),
        "workspace-1",
    )

    assert ir.state == "unresolved"
    assert not ir.nodes


def test_unsupported_relation_vocabulary_fails_closed_before_planning():
    understanding = SemanticUnderstanding(
        state="resolved",
        entities=(
            SemanticEntity(
                reference_id="parent",
                mention="Parent A",
                entity_type="person",
                resolution="resolved",
                canonical_entity_id="person-1",
            ),
        ),
        relations=(
            SemanticRelation(
                predicate="favorite_teacher_of",
                subject_reference_id="parent",
                target_entity_type="person",
            ),
        ),
        operators=("traverse_relation",),
        confidence=1.0,
    )

    with pytest.raises(IRValidationError, match="relation is not declared"):
        validate_logical_ir(
            lower_semantic_understanding(understanding, "workspace-1"), IRVocabulary.core()
        )


def test_semantic_ambiguity_yields_candidate_plans_and_underspecified_work_stays_unresolved():
    candidates = tuple(
        InterpretationCandidate(
            label=f"person {ordinal}",
            explanation="different conversation referent",
            entities=(
                SemanticEntity(
                    reference_id="person",
                    mention="he",
                    entity_type="person",
                    resolution="resolved",
                    canonical_entity_id=f"person-{ordinal}",
                ),
            ),
            targets=(
                SemanticTarget(
                    target_type="entity", reference_id="person", description="candidate person"
                ),
            ),
            operators=("retrieve_evidence", "summarize"),
            confidence=0.5,
        )
        for ordinal in (1, 2)
    )
    ambiguous = SemanticUnderstanding(
        state="ambiguous",
        candidates=candidates,
        ambiguity_reasons=("two people remain",),
        confidence=0.5,
    )
    candidate_ir = lower_semantic_understanding(ambiguous, "workspace-1")
    assert candidate_ir.state == "ambiguous"
    assert len(candidate_ir.candidate_plans) == 2
    validate_logical_ir(candidate_ir, IRVocabulary.core())

    underspecified = SemanticUnderstanding(
        state="resolved",
        targets=(SemanticTarget(target_type="property", description="properties"),),
        operators=("aggregate",),
        coverage="corpus_required",
        confidence=0.8,
    )
    unresolved_ir = lower_semantic_understanding(underspecified, "workspace-1")
    assert unresolved_ir.state == "unresolved"
    assert "typed arguments" in unresolved_ir.issues[0]
