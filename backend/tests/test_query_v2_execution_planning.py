import json

import pytest

from app.query.ir import (
    CandidateLogicalPlan,
    CompareNode,
    CountNode,
    CoverageContract,
    CustomCapabilityNode,
    EventSetNode,
    IRVocabulary,
    LogicalQueryIR,
    OutputProjection,
    RelationDeclaration,
    RelationReference,
    ResolveNode,
    RetrieveEvidenceNode,
    ScanNode,
    SummarizeNode,
    TemporalConstraintNode,
    TemporalPredicate,
    TraverseNode,
)
from app.query.planning import (
    DEFAULT_CAPABILITIES,
    CapabilityDeclaration,
    CapabilityReadiness,
    PhysicalExecutionPlan,
    PlanningReadinessSnapshot,
    plan_execution,
)

WORKSPACE = "workspace-1"
GENERATION = "generation-7"


def _vocabulary(*custom: str) -> IRVocabulary:
    core = IRVocabulary.core()
    return IRVocabulary(
        resources=core.resources,
        relations={
            "owns": RelationDeclaration(
                source_resources=frozenset({"person"}),
                target_resources=frozenset({"asset_property"}),
            )
        },
        custom_capabilities=frozenset(custom),
    )


def _snapshot(
    *,
    unavailable: frozenset[str] = frozenset(),
    generation: str | None = GENERATION,
    capabilities: tuple[CapabilityDeclaration, ...] = DEFAULT_CAPABILITIES,
) -> PlanningReadinessSnapshot:
    return PlanningReadinessSnapshot(
        workspace_id=WORKSPACE,
        active_generation_id=generation,
        capabilities=tuple(
            CapabilityReadiness(
                workspace_id=WORKSPACE,
                engine=item.engine,
                capability=item.capability,
                state="unavailable" if item.capability in unavailable else "ready",
                generation_id=generation if item.requires_generation else None,
            )
            for item in capabilities
        ),
    )


def _grounded(nodes, root: str, shape: str = "evidence") -> LogicalQueryIR:
    return LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=tuple(nodes),
        root_ids=(root,),
        output=OutputProjection(shape=shape),
    )


def test_physical_schema_is_a_versioned_dag_not_an_intent_route_tuple():
    schema = json.dumps(PhysicalExecutionPlan.model_json_schema()).casefold()

    assert '"1.0"' in schema
    assert '"dependencies"' in schema
    assert '"capability"' in schema
    assert '"readiness"' in schema
    assert '"failure_policy"' in schema
    assert '"trace"' in schema
    assert '"intent"' not in schema
    assert '"route"' not in schema


def test_exact_event_population_temporal_plan_uses_graph_filter_not_structured():
    events = EventSetNode(node_id="events")
    temporal = TemporalConstraintNode(
        node_id="events_on_date", inputs=("events",), output_type="event_set",
        predicates=(TemporalPredicate(role="event_date", original_text="12.06.1974",
            normalized_start="1974-06-12", normalized_end="1974-06-12", precision="day",
            uncertainty="certain"),),
    )
    ir = _grounded((events, temporal), "events_on_date", shape="rows")

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.state == "ready" and plan.graph is not None
    assert [step.capability for step in plan.graph.steps[:-1]] == [
        "graph.event_population", "graph.event_filter"
    ]
    assert "structured.temporal_filter" not in [step.capability for step in plan.graph.steps]
    assert plan.graph.steps[1].dependencies == ("execute.events",)


def test_exhaustive_count_uses_one_generation_and_mandatory_reconciliation():
    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=(
            ScanNode(
                node_id="properties",
                workspace_id=WORKSPACE,
                resource="asset_property",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
            CountNode(node_id="total", inputs=("properties",), output_type="scalar"),
        ),
        root_ids=("total",),
        output=OutputProjection(shape="scalar"),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="all active workspace properties",
            same_generation_required=True,
            partial_results_allowed=False,
        ),
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.state == "ready"
    assert plan.graph is not None
    assert [step.capability for step in plan.graph.steps] == [
        "structured.enumerate",
        "structured.count",
        "evidence.reconcile_and_validate",
    ]
    assert {step.readiness.generation_id for step in plan.graph.steps[:-1]} == {GENERATION}
    assert plan.graph.steps[-1].failure_policy.action == "fail_closed"


def test_exhaustive_canonical_query_fails_closed_when_canonical_is_unavailable():
    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=(
            ScanNode(
                node_id="people",
                workspace_id=WORKSPACE,
                resource="person",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
        ),
        root_ids=("people",),
        output=OutputProjection(shape="entities"),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="all active workspace people",
            same_generation_required=True,
            partial_results_allowed=False,
        ),
    )

    plan = plan_execution(
        ir, _vocabulary(), _snapshot(unavailable=frozenset({"structured.enumerate"}))
    )

    assert plan.state == "unsupported"
    assert "no ready capability" in plan.issues[0]


def test_relation_traversal_fails_closed_when_canonical_graph_is_unavailable():
    ir = _grounded(
        (
            ResolveNode(
                node_id="person",
                workspace_id=WORKSPACE,
                resource="person",
                reference_id="person_ref",
                mention="Ada",
                canonical_entity_ids=("person-1",),
            ),
            TraverseNode(
                node_id="properties",
                inputs=("person",),
                output_type="graph_paths",
                relation=RelationReference(
                    relation="owns", source_resource="person", target_resource="asset_property"
                ),
            ),
        ),
        "properties",
        "rows",
    )

    plan = plan_execution(
        ir,
        _vocabulary(),
        _snapshot(unavailable=frozenset({"graph.entity_resolve", "graph.traverse"})),
    )

    assert plan.state == "unsupported"
    assert "no ready capability" in plan.issues[0]


def test_graph_retrieval_and_synthesis_form_a_dependent_multi_engine_plan():
    ir = _grounded(
        (
            ResolveNode(
                node_id="person",
                workspace_id=WORKSPACE,
                resource="person",
                reference_id="person_ref",
                mention="Berke",
                canonical_entity_ids=("person-1",),
            ),
            TraverseNode(
                node_id="properties",
                inputs=("person",),
                output_type="graph_paths",
                relation=RelationReference(
                    relation="owns", source_resource="person", target_resource="asset_property"
                ),
                maximum_hops=3,
            ),
            RetrieveEvidenceNode(node_id="evidence", inputs=("properties",)),
            SummarizeNode(node_id="summary", inputs=("evidence",)),
        ),
        "summary",
        "summary",
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.graph is not None
    steps = {step.step_id: step for step in plan.graph.steps}
    engines = [
        steps[f"execute.{name}"].engine
        for name in ("person", "properties", "evidence", "summary")
    ]
    assert engines == [
        "knowledge_graph",
        "knowledge_graph",
        "retrieval",
        "reasoning",
    ]
    assert steps["execute.properties"].capability == "graph.multi_hop"
    assert steps["execute.evidence"].dependencies == ("execute.properties",)
    assert steps["execute.summary"].dependencies == ("execute.evidence",)
    assert steps["execute.reconcile"].dependencies == ("execute.summary",)


def test_temporal_relative_constraints_use_graph_reasoning():
    ir = _grounded(
        (
            ResolveNode(
                node_id="event_entities",
                workspace_id=WORKSPACE,
                resource="event",
                reference_id="event_ref",
                mention="the sale",
                canonical_entity_ids=("event-1",),
            ),
            TemporalConstraintNode(
                node_id="before_sale",
                inputs=("event_entities",),
                output_type="entity_set",
                predicates=(
                    TemporalPredicate(
                        role="before_event",
                        original_text="before the sale",
                        precision="unknown",
                        uncertainty="unknown",
                        anchor_event="the sale",
                    ),
                ),
            ),
        ),
        "before_sale",
        "entities",
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.graph is not None
    assert plan.graph.steps[1].capability == "graph.temporal_reasoning"


def test_graphrag_modes_contradiction_and_research_are_capabilities():
    for capability in (
        "graphrag.local",
        "graphrag.global",
        "graphrag.drift",
        "graphrag.community_context",
        "graph.contradiction_analysis",
        "reasoning.long_form_research",
    ):
        ir = _grounded(
            (
                CustomCapabilityNode(node_id="special", capability=capability),
                SummarizeNode(node_id="summary", inputs=("special",)),
            ),
            "summary",
            "summary",
        )
        plan = plan_execution(ir, _vocabulary(capability), _snapshot())
        assert plan.graph is not None
        assert plan.graph.steps[0].capability == capability


def test_generation_mismatch_fails_closed_for_exhaustive_work():
    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=(
            ScanNode(
                node_id="properties",
                workspace_id=WORKSPACE,
                resource="asset_property",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
        ),
        root_ids=("properties",),
        output=OutputProjection(shape="entities"),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="all active workspace properties",
            same_generation_required=True,
            partial_results_allowed=False,
        ),
    )
    snapshot = _snapshot().model_copy(update={"active_generation_id": "generation-8"})

    plan = plan_execution(ir, _vocabulary(), snapshot)

    assert plan.state == "unsupported"
    assert "no ready capability" in plan.issues[0]


def test_grounded_retrieval_can_select_declared_semantic_degradation():
    ir = _grounded(
        (
            ScanNode(
                node_id="documents",
                workspace_id=WORKSPACE,
                resource="document",
                output_type="document_set",
            ),
            RetrieveEvidenceNode(node_id="evidence", inputs=("documents",)),
        ),
        "evidence",
    )

    plan = plan_execution(
        ir,
        _vocabulary(),
        _snapshot(unavailable=frozenset({"retrieval.hybrid_search"})),
    )

    assert plan.graph is not None
    assert plan.graph.steps[1].capability == "retrieval.semantic_search"
    assert plan.graph.steps[1].failure_policy.action == "return_partial"


def test_cost_is_only_the_last_selection_dimension():
    base = next(item for item in DEFAULT_CAPABILITIES if item.capability == "graphrag.local")
    expensive_better = base.model_copy(
        update={"engine": "quality_engine", "reasoning_quality": 100, "cost": 100}
    )
    cheap_weaker = base.model_copy(
        update={"engine": "cheap_engine", "reasoning_quality": 99, "cost": 1}
    )
    reconciliation = next(
        item
        for item in DEFAULT_CAPABILITIES
        if item.capability == "evidence.reconcile_and_validate"
    )
    synthesis = next(
        item for item in DEFAULT_CAPABILITIES if item.capability == "reasoning.evidence_synthesis"
    )
    capabilities = (expensive_better, cheap_weaker, synthesis, reconciliation)
    ir = _grounded(
        (
            CustomCapabilityNode(node_id="local", capability="graphrag.local"),
            SummarizeNode(node_id="summary", inputs=("local",)),
        ),
        "summary",
        "summary",
    )

    plan = plan_execution(
        ir, _vocabulary("graphrag.local"), _snapshot(capabilities=capabilities), capabilities
    )

    assert plan.graph is not None
    assert plan.graph.steps[0].engine == "quality_engine"


def test_readiness_snapshot_cannot_cross_workspace_boundaries():
    with pytest.raises(ValueError, match="workspace boundary"):
        PlanningReadinessSnapshot(
            workspace_id=WORKSPACE,
            capabilities=(
                CapabilityReadiness(
                    workspace_id="workspace-2",
                    engine="retrieval",
                    capability="retrieval.hybrid_search",
                    state="ready",
                    generation_id=GENERATION,
                ),
            ),
        )


def test_ambiguous_meanings_remain_separate_candidate_dags():
    def candidate(label: str, resource: str, confidence: float) -> CandidateLogicalPlan:
        scan_id = f"scan_{resource}"
        return CandidateLogicalPlan(
            label=label,
            explanation=f"Interpret the reference as {resource}",
            confidence=confidence,
            nodes=(
                ScanNode(
                    node_id=scan_id,
                    workspace_id=WORKSPACE,
                    resource=resource,
                    output_type="document_set" if resource == "document" else "entity_set",
                ),
                RetrieveEvidenceNode(node_id=f"evidence_{resource}", inputs=(scan_id,)),
            ),
            root_ids=(f"evidence_{resource}",),
            output=OutputProjection(shape="evidence"),
        )

    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="ambiguous",
        candidate_plans=(
            candidate("document", "document", 0.55),
            candidate("person", "person", 0.45),
        ),
        issues=("the reference may identify a document or a person",),
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.state == "ambiguous"
    assert [item.label for item in plan.candidate_plans] == ["document", "person"]
    assert all(
        item.steps[-1].capability == "evidence.reconcile_and_validate"
        for item in plan.candidate_plans
    )


def test_population_comparison_preserves_parallel_upstream_branches():
    coverage = CoverageContract(
        mode="exhaustive",
        population_boundary="all active people and organizations",
        same_generation_required=True,
        partial_results_allowed=False,
    )
    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=(
            ScanNode(
                node_id="people",
                workspace_id=WORKSPACE,
                resource="person",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
            ScanNode(
                node_id="organizations",
                workspace_id=WORKSPACE,
                resource="organization",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
            CompareNode(
                node_id="compare",
                inputs=("people", "organizations"),
                comparison="populations",
            ),
        ),
        root_ids=("compare",),
        output=OutputProjection(shape="comparison"),
        coverage=coverage,
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.graph is not None
    compare = next(step for step in plan.graph.steps if step.step_id == "execute.compare")
    assert compare.dependencies == ("execute.people", "execute.organizations")


def test_missing_mandatory_projection_makes_plan_unsupported():
    ir = LogicalQueryIR(
        workspace_id=WORKSPACE,
        state="resolved",
        nodes=(
            ScanNode(
                node_id="people",
                workspace_id=WORKSPACE,
                resource="person",
                output_type="entity_set",
                population_mode="exhaustive",
            ),
        ),
        root_ids=("people",),
        output=OutputProjection(shape="entities"),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="all active documents",
            same_generation_required=True,
            mandatory_projections=("canonical_documents",),
            partial_results_allowed=False,
        ),
    )

    plan = plan_execution(ir, _vocabulary(), _snapshot())

    assert plan.state == "unsupported"
    assert "no ready capability" in plan.issues[0]
