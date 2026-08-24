from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.engines.graph import GraphExecutionError, KnowledgeGraphEngine
from app.knowledge.graph import CanonicalEventQueryView, CanonicalEvidenceQueryView
from app.query.execution import (
    EngineExecutionOutput,
    ProductionEngineRegistry,
    V2DenseAdapter,
    V2PlanExecutor,
)
from app.query.ir.schemas import EventSetNode, ScanNode, TemporalConstraintNode, TemporalPredicate
from app.query.orchestration import (
    CompletenessReport,
    EngineResult,
    EngineTrace,
    ExpectedResultStep,
    ProvenanceLink,
    ReconciliationContract,
    TrustedSource,
    reconcile_engine_results,
)
from app.query.planning import (
    ExecutionPlanGraph,
    ExecutionStep,
    FailurePolicy,
    PhysicalExecutionPlan,
    PlanTrace,
    ReadinessRequirement,
)
from app.query.production_engines import GraphProductionEngine
from app.query.scope import GenerationScope
from app.query.service import _final_result_steps


class FixedScope:
    def __init__(self):
        self.scope = GenerationScope("workspace", "generation", "embedding")

    def resolve(self, workspace_id):
        assert workspace_id == self.scope.workspace_id
        return self.scope


class EmptyDense:
    def search_generation(self, query_vector, limit, scope):
        return []


class RecordingEngine:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def execute(self, context):
        self.calls.append((self.name, context.step.step_id, context.dependency_values))
        result = EngineResult(
            result_id=f"result-{context.step.step_id}",
            workspace_id=context.scope.workspace_id,
            generation_id=context.scope.generation_id,
            step_id=context.step.step_id,
            engine=context.step.engine,
            capability=context.step.capability,
            state="success",
            completeness=CompletenessReport(
                coverage="grounded", state="unknown", generation_id=context.scope.generation_id
            ),
            confidence=1.0,
            trace=EngineTrace(
                step_id=context.step.step_id,
                engine=context.step.engine,
                capability=context.step.capability,
                duration_ms=0,
            ),
        )
        return EngineExecutionOutput(context.step.step_id, result)


def _step(step_id, engine, capability, node_id, dependencies=()):
    return ExecutionStep(
        step_id=step_id,
        engine=engine,
        capability=capability,
        dependencies=dependencies,
        output_type="entity_set",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace", generation_id="generation"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=(node_id,), selection_reason="test"),
    )


def test_registry_executes_multi_engine_dependencies_in_plan_order():
    first_node = ScanNode(
        node_id="scan", workspace_id="workspace", resource="entity", output_type="entity_set"
    )
    second_node = ScanNode(
        node_id="graph", workspace_id="workspace", resource="entity", output_type="entity_set"
    )
    first = _step("execute.scan", "structured", "structured.enumerate", "scan")
    second = _step(
        "execute.graph", "knowledge_graph", "graph.entity_resolve", "graph", (first.step_id,)
    )
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(steps=(first, second), root_step_ids=(second.step_id,)),
    )
    calls = []
    registry = ProductionEngineRegistry(
        {
            "structured": RecordingEngine("structured", calls),
            "knowledge_graph": RecordingEngine("knowledge_graph", calls),
        }
    )
    executor = V2PlanExecutor(FixedScope(), V2DenseAdapter(EmptyDense()), registry=registry)

    result = executor.execute_plan(
        plan, (first_node, second_node), query_vector=None, query_text=None, trusted_sources=()
    )

    assert [item.engine for item in result.results] == ["structured", "knowledge_graph"]
    assert calls == [
        ("structured", "execute.scan", ()),
        ("knowledge_graph", "execute.graph", ("execute.scan",)),
    ]


def _event_evidence():
    return CanonicalEvidenceQueryView(
        "event-evidence", "document", "version", "logical", "chunk", 0, 9,
        "Event One", 0.9, "generation",
    )


@dataclass
class EventGraphReader:
    workspace_id: str = "workspace"
    event_calls: list[tuple[str, str]] = field(default_factory=list)
    path_calls: int = 0

    def query_canonical_events(self, generation, *, event_date, limit=500):
        self.event_calls.append((generation, event_date))
        return (
            CanonicalEventQueryView(
                "E1", "generic_event", "Event One", event_date, ("P1", "P2"),
                (_event_evidence(),),
            ),
        )

    def query_event_paths(self, *args, **kwargs):
        self.path_calls += 1
        raise AssertionError("unanchored event filter must not query event paths")


def _event_filter_step(step_id, node_id, dependencies=()):
    return _step(step_id, "knowledge_graph", "graph.event_filter", node_id, dependencies)


def test_executor_routes_event_filter_to_graph_engine_once_without_fallbacks():
    population = EventSetNode(node_id="events")
    event_filter = TemporalConstraintNode(
        node_id="on_date",
        inputs=(population.node_id,),
        output_type="event_set",
        predicates=(
            TemporalPredicate(
                role="event_date", original_text="12 June 1974",
                normalized_start="1974-06-12", normalized_end="1974-06-12",
                precision="day", uncertainty="certain",
            ),
        ),
    )
    population_step = _step(
        "execute.events", "knowledge_graph", "graph.event_population", population.node_id
    )
    filter_step = _event_filter_step(
        "execute.on_date", event_filter.node_id, (population_step.step_id,)
    )
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(
            steps=(population_step, filter_step), root_step_ids=(filter_step.step_id,)
        ),
    )
    reader = EventGraphReader()
    graph_engine = GraphProductionEngine(lambda scope: reader)
    registry = ProductionEngineRegistry({"knowledge_graph": graph_engine})

    execution = V2PlanExecutor(
        FixedScope(), V2DenseAdapter(EmptyDense()), registry=registry
    ).execute_plan(
        plan, (population, event_filter), query_vector=None, query_text=None, trusted_sources=()
    )

    assert registry.engine_for("knowledge_graph") is graph_engine
    assert reader.event_calls == [("generation", "1974-06-12")]
    assert reader.path_calls == 0
    assert execution.scope == FixedScope().scope
    result = execution.results[-1]
    assert result.events[0].event_id == "E1"
    assert result.events[0].event_type == "generic_event"
    assert result.events[0].event_name == "Event One"
    assert result.events[0].event_date == "1974-06-12"
    assert result.events[0].participant_canonical_ids == ("P1", "P2")
    assert result.text_evidence[0].evidence_id == "event-evidence"
    assert result.workspace_id == "workspace"
    assert result.generation_id == "generation"


def _event_source():
    return TrustedSource(
        workspace_id="workspace",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk",
        content="Event One",
        generation_id="generation",
        citation_label="Event register",
    )


def _event_contract(*step_ids):
    return ReconciliationContract(
        workspace_id="workspace",
        generation_id="generation",
        coverage="grounded",
        expected_steps=tuple(
            ExpectedResultStep(
                step_id=step_id, engine="knowledge_graph", capability="graph.event_filter"
            )
            for step_id in step_ids
        ),
    )


def test_event_results_reconcile_deduplicate_and_preserve_reasoning_package_fields():
    population, event_filter, plan, reader = _event_filter_execution_fixture()
    execution = V2PlanExecutor(
        FixedScope(), V2DenseAdapter(EmptyDense()),
        registry=ProductionEngineRegistry(
            {"knowledge_graph": GraphProductionEngine(lambda _: reader)}
        ),
    ).execute_plan(
        plan, (population, event_filter), query_vector=None, query_text=None, trusted_sources=()
    )
    population_result, filtered_result = execution.results
    assert population_result.events == ()
    duplicate_evidence = filtered_result.text_evidence[0].model_copy(
        update={"evidence_id": "event-evidence-duplicate"}
    )
    duplicate_event = filtered_result.events[0].model_copy(
        update={"evidence_ids": (duplicate_evidence.evidence_id,)}
    )
    duplicate = filtered_result.model_copy(
        update={
            "result_id": "result-execute.duplicate",
            "step_id": "execute.duplicate",
            "text_evidence": (duplicate_evidence,),
            "events": (duplicate_event,),
            "provenance": (
                ProvenanceLink(result_id="E1", evidence_ids=(duplicate_evidence.evidence_id,)),
            ),
            "trace": filtered_result.trace.model_copy(update={"step_id": "execute.duplicate"}),
        }
    )
    package = reconcile_engine_results(
        _event_contract(filtered_result.step_id, duplicate.step_id),
        (filtered_result, duplicate),
        (_event_source(),),
    )

    assert [item.event_id for item in package.events] == ["E1"]
    event = package.events[0]
    assert (event.event_type, event.event_name, event.event_date) == (
        "generic_event", "Event One", "1974-06-12"
    )
    assert event.participant_canonical_ids == ("P1", "P2")
    assert event.workspace_id == package.workspace_id == "workspace"
    assert event.generation_id == package.generation_id == "generation"
    assert event.evidence_ids == ("event-evidence",)
    assert package.citations[0].evidence_id == "event-evidence"


def test_event_filter_is_the_only_final_root_result_not_event_population():
    population, event_filter, plan, _ = _event_filter_execution_fixture()

    result_steps = _final_result_steps(
        plan, SimpleNamespace(root_ids=(event_filter.node_id,))
    )

    assert result_steps == {"execute.on_date"}
    assert "execute.events" not in result_steps


def _event_filter_execution_fixture():
    population = EventSetNode(node_id="events")
    event_filter = TemporalConstraintNode(
        node_id="on_date",
        inputs=(population.node_id,),
        output_type="event_set",
        predicates=(
            TemporalPredicate(
                role="event_date", original_text="12 June 1974",
                normalized_start="1974-06-12", normalized_end="1974-06-12",
                precision="day", uncertainty="certain",
            ),
        ),
    )
    population_step = _step(
        "execute.events", "knowledge_graph", "graph.event_population", population.node_id
    )
    filter_step = _event_filter_step(
        "execute.on_date", event_filter.node_id, (population_step.step_id,)
    )
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(
            steps=(population_step, filter_step), root_step_ids=(filter_step.step_id,)
        ),
    )
    return population, event_filter, plan, EventGraphReader()


def test_executor_fails_closed_when_graph_engine_is_unregistered():
    node = EventSetNode(node_id="events")
    step = _step("execute.events", "knowledge_graph", "graph.event_population", node.node_id)
    plan = PhysicalExecutionPlan(
        workspace_id="workspace", state="ready",
        graph=ExecutionPlanGraph(steps=(step,), root_step_ids=(step.step_id,)),
    )

    with pytest.raises(ValueError, match="V2_ENGINE_NOT_REGISTERED:knowledge_graph"):
        V2PlanExecutor(
            FixedScope(), V2DenseAdapter(EmptyDense()),
            registry=ProductionEngineRegistry({}),
        ).execute_plan(
            plan, (node,), query_vector=None, query_text=None, trusted_sources=()
        )


def test_graph_event_filter_rejects_invalid_date_without_adapter_call():
    node = TemporalConstraintNode(
        node_id="on_date",
        inputs=("events",),
        output_type="event_set",
        predicates=(
            TemporalPredicate(
                role="event_date", original_text="invalid date",
                normalized_start="1974-99-12", normalized_end="1974-99-12",
                precision="day", uncertainty="certain",
            ),
        ),
    )
    reader = EventGraphReader()

    with pytest.raises(GraphExecutionError, match="exact event_date ISO day"):
        KnowledgeGraphEngine("workspace", "generation", reader).execute(
            _event_filter_step("execute.on_date", node.node_id), node
        )

    assert reader.event_calls == []
    assert reader.path_calls == 0
