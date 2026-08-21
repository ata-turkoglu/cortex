"""Correctness-first lowering from Logical Query IR to a physical execution DAG."""

from __future__ import annotations

from dataclasses import dataclass

from app.query.ir import IRVocabulary, LogicalPlanGraph, LogicalQueryIR, validate_logical_ir
from app.query.ir.schemas import (
    CustomCapabilityNode,
    IRNode,
    SummarizeNode,
    TemporalConstraintNode,
    TraverseNode,
)

from .capabilities import DEFAULT_CAPABILITIES
from .schemas import (
    CapabilityDeclaration,
    CapabilityReadiness,
    ExecutionPlanGraph,
    ExecutionStep,
    FailurePolicy,
    FallbackOption,
    PhysicalExecutionPlan,
    PlanningReadinessSnapshot,
    PlanTrace,
    ReadinessRequirement,
)


class ExecutionPlanningError(ValueError):
    pass


@dataclass(frozen=True)
class _Selection:
    declaration: CapabilityDeclaration
    readiness: CapabilityReadiness
    fallbacks: tuple[FallbackOption, ...]


def plan_execution(
    ir: LogicalQueryIR,
    vocabulary: IRVocabulary,
    readiness: PlanningReadinessSnapshot,
    capabilities: tuple[CapabilityDeclaration, ...] = DEFAULT_CAPABILITIES,
) -> PhysicalExecutionPlan:
    """Build a plan without opening storage transactions or invoking any engine."""
    if readiness.workspace_id != ir.workspace_id:
        raise ExecutionPlanningError("readiness snapshot crosses the IR workspace boundary")
    validate_logical_ir(ir, vocabulary)
    if ir.state == "unresolved":
        return PhysicalExecutionPlan(
            workspace_id=ir.workspace_id, state="unresolved", issues=ir.issues
        )
    if ir.state == "ambiguous":
        candidates: list[ExecutionPlanGraph] = []
        issues = list(ir.issues)
        for candidate in ir.candidate_plans:
            try:
                graph = _plan_graph(ir, candidate, readiness, capabilities)
            except ExecutionPlanningError as error:
                issues.append(f"candidate {candidate.label}: {error}")
                continue
            candidates.append(
                graph.model_copy(
                    update={"label": candidate.label, "confidence": candidate.confidence}
                )
            )
        if len(candidates) < 2:
            return PhysicalExecutionPlan(
                workspace_id=ir.workspace_id,
                state="unsupported",
                issues=tuple(issues + ["fewer than two executable interpretations remain"]),
            )
        return PhysicalExecutionPlan(
            workspace_id=ir.workspace_id,
            state="ambiguous",
            candidate_plans=tuple(candidates),
            issues=ir.issues,
        )
    graph = LogicalPlanGraph(nodes=ir.nodes, root_ids=ir.root_ids, output=ir.output)  # type: ignore[arg-type]
    try:
        physical = _plan_graph(ir, graph, readiness, capabilities)
    except ExecutionPlanningError as error:
        return PhysicalExecutionPlan(
            workspace_id=ir.workspace_id, state="unsupported", issues=(str(error),)
        )
    return PhysicalExecutionPlan(workspace_id=ir.workspace_id, state="ready", graph=physical)


def _plan_graph(
    ir: LogicalQueryIR,
    graph: LogicalPlanGraph,
    readiness: PlanningReadinessSnapshot,
    capabilities: tuple[CapabilityDeclaration, ...],
) -> ExecutionPlanGraph:
    nodes = {node.node_id: node for node in graph.nodes}
    steps: list[ExecutionStep] = []
    step_by_node: dict[str, ExecutionStep] = {}
    for node in graph.nodes:
        candidates = _capability_candidates(node, nodes)
        selection = _select(candidates, node, ir, readiness, capabilities)
        step = _step(node, selection, ir, step_by_node)
        steps.append(step)
        step_by_node[node.node_id] = step

    root_steps = tuple(step_by_node[root_id].step_id for root_id in graph.root_ids)
    reconciliation = _reconciliation_step(ir, graph, root_steps, readiness, capabilities)
    steps.append(reconciliation)
    return ExecutionPlanGraph(steps=tuple(steps), root_step_ids=(reconciliation.step_id,))


def _capability_candidates(node: IRNode, nodes: dict[str, IRNode]) -> tuple[str, ...]:
    direct = {
        "scan": "structured.enumerate",
        "resolve": "graph.entity_resolve",
        "filter": "structured.filter",
        "join": "structured.join",
        "distinct": "structured.distinct",
        "group": "structured.group",
        "aggregate": "structured.aggregate",
        "count": "structured.count",
        "rank": "structured.rank",
        "sort": "structured.sort",
        "limit": "structured.limit",
        "project": "structured.project",
        "compare": "structured.compare",
        "exists": "structured.exists",
    }
    if isinstance(node, TraverseNode):
        return ("graph.multi_hop" if node.maximum_hops > 1 else "graph.traverse",)
    if isinstance(node, TemporalConstraintNode):
        relative = any(item.role in {"before_event", "after_event"} for item in node.predicates)
        graph_input = any(isinstance(nodes[item], TraverseNode) for item in node.inputs)
        return (
            ("graph.temporal_reasoning",)
            if relative or graph_input
            else ("structured.temporal_filter",)
        )
    if node.kind == "retrieve_evidence":
        return ("retrieval.hybrid_search", "retrieval.semantic_search")
    if isinstance(node, SummarizeNode):
        return ("reasoning.evidence_synthesis",)
    if isinstance(node, CustomCapabilityNode):
        return (node.capability,)
    return (direct[node.kind],)


def _select(
    candidate_names: tuple[str, ...],
    node: IRNode,
    ir: LogicalQueryIR,
    snapshot: PlanningReadinessSnapshot,
    declarations: tuple[CapabilityDeclaration, ...],
    *,
    expected_output: str | None = None,
) -> _Selection:
    required_coverage = "exhaustive" if ir.coverage.mode == "exhaustive" else "grounded"
    declared = [item for item in declarations if item.capability in candidate_names]
    compatible = [
        item
        for item in declared
        if (expected_output or node.output_type) in item.output_types
        and (required_coverage != "exhaustive" or item.maximum_coverage == "exhaustive")
    ]
    ready: list[tuple[CapabilityDeclaration, CapabilityReadiness]] = []
    for item in compatible:
        state = _readiness(item, snapshot)
        if state is None or state.state != "ready":
            continue
        if item.requires_generation and (
            snapshot.active_generation_id is None
            or state.generation_id != snapshot.active_generation_id
        ):
            continue
        required_projections = set(item.required_projections)
        if item.requires_generation:
            required_projections.update(ir.coverage.mandatory_projections)
        if not required_projections.issubset(state.ready_projections):
            continue
        ready.append((item, state))
    if not ready:
        raise ExecutionPlanningError(
            f"no ready capability preserves {required_coverage} coverage for {node.node_id}"
        )
    ready.sort(key=lambda pair: _score(pair[0]), reverse=True)
    selected, state = ready[0]
    fallbacks = tuple(
        FallbackOption(
            engine=item.engine,
            capability=item.capability,
            preserves_correctness=item.correctness >= selected.correctness,
            preserves_coverage=(
                required_coverage != "exhaustive" or item.maximum_coverage == "exhaustive"
            ),
        )
        for item, _ in ready[1:]
        if item.correctness >= selected.correctness
    )
    return _Selection(selected, state, fallbacks)


def _score(item: CapabilityDeclaration) -> tuple[int, int, int, int, int, int]:
    return (
        item.correctness,
        item.evidence_quality,
        item.coverage_quality,
        item.reasoning_quality,
        -item.latency,
        -item.cost,
    )


def _readiness(
    declaration: CapabilityDeclaration, snapshot: PlanningReadinessSnapshot
) -> CapabilityReadiness | None:
    return next(
        (
            item
            for item in snapshot.capabilities
            if item.engine == declaration.engine and item.capability == declaration.capability
        ),
        None,
    )


def _step(
    node: IRNode,
    selection: _Selection,
    ir: LogicalQueryIR,
    step_by_node: dict[str, ExecutionStep],
) -> ExecutionStep:
    declaration = selection.declaration
    dependencies = tuple(step_by_node[item].step_id for item in node.inputs)
    input_types = tuple(step_by_node[item].output_type for item in node.inputs)
    return ExecutionStep(
        step_id=f"execute.{node.node_id}",
        engine=declaration.engine,
        capability=declaration.capability,
        dependencies=dependencies,
        input_types=input_types,
        output_type=node.output_type,
        coverage_expectation=("exhaustive" if ir.coverage.mode == "exhaustive" else "grounded"),
        readiness=ReadinessRequirement(
            workspace_id=ir.workspace_id,
            generation_id=(
                selection.readiness.generation_id if declaration.requires_generation else None
            ),
            projections=tuple(
                sorted(
                    set(declaration.required_projections)
                    | set(ir.coverage.mandatory_projections)
                )
            ),
        ),
        failure_policy=FailurePolicy(
            action=("return_partial" if ir.coverage.partial_results_allowed else "fail_closed"),
            fallback_options=selection.fallbacks,
        ),
        trace=PlanTrace(
            logical_node_ids=(node.node_id,),
            selection_reason=(
                "highest lexicographic capability score among ready, coverage-compatible "
                "workspace generation candidates"
            ),
        ),
    )


def _reconciliation_step(
    ir: LogicalQueryIR,
    graph: LogicalPlanGraph,
    roots: tuple[str, ...],
    snapshot: PlanningReadinessSnapshot,
    declarations: tuple[CapabilityDeclaration, ...],
) -> ExecutionStep:
    synthetic = CustomCapabilityNode(
        node_id="reconcile", inputs=(), capability="evidence.reconcile_and_validate"
    )
    selection = _select(
        (synthetic.capability,),
        synthetic,
        ir,
        snapshot,
        declarations,
        expected_output="evidence_package",
    )
    root_nodes = {node.node_id: node for node in graph.nodes}
    return ExecutionStep(
        step_id="execute.reconcile",
        engine=selection.declaration.engine,
        capability=selection.declaration.capability,
        dependencies=roots,
        input_types=tuple(root_nodes[item].output_type for item in graph.root_ids),
        output_type="evidence_package",
        coverage_expectation=("exhaustive" if ir.coverage.mode == "exhaustive" else "grounded"),
        readiness=ReadinessRequirement(workspace_id=ir.workspace_id),
        failure_policy=FailurePolicy(action="fail_closed", fallback_options=selection.fallbacks),
        trace=PlanTrace(
            logical_node_ids=graph.root_ids,
            selection_reason="mandatory evidence reconciliation and coverage validation boundary",
        ),
    )
