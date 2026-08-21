"""Semantic, vocabulary, scope, type, and coverage validation for Logical Query IR."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from pydantic import ValidationError

from .schemas import (
    AggregateNode,
    CompareNode,
    CountNode,
    CustomCapabilityNode,
    DistinctNode,
    ExistsNode,
    FieldReference,
    FilterNode,
    GroupNode,
    IRNode,
    JoinNode,
    LimitNode,
    LogicalPlanGraph,
    LogicalQueryIR,
    ProjectNode,
    RankNode,
    RelationReference,
    ResolveNode,
    RetrieveEvidenceNode,
    ScanNode,
    SortNode,
    SummarizeNode,
    TemporalConstraintNode,
    TraverseNode,
    ValueType,
)


class IRValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RelationDeclaration:
    source_resources: frozenset[str]
    target_resources: frozenset[str]


@dataclass(frozen=True)
class IRVocabulary:
    """Workspace schema snapshot used to validate dynamic, governed extensions."""

    resources: dict[str, frozenset[str]]
    relations: dict[str, RelationDeclaration] = field(default_factory=dict)
    custom_capabilities: frozenset[str] = frozenset()

    @classmethod
    def core(cls) -> IRVocabulary:
        common_entity = frozenset(
            {"entity_id", "entity_type", "display_name", "subtype", "status"}
        )
        resources = {
            "entity": common_entity,
            "person": common_entity,
            "organization": common_entity,
            "location": common_entity,
            "asset_property": common_entity
            | {"province", "district", "neighborhood", "pafta", "ada", "parcel", "section"},
            "document": frozenset(
                {"document_id", "title", "created_at", "active_version_id", "state"}
            ),
            "logical_document": frozenset(
                {"logical_document_id", "document_id", "code", "title", "ordinal"}
            ),
            "event": frozenset({"event_id", "event_type", "name", "status"}),
            "temporal_expression": frozenset(
                {
                    "temporal_id",
                    "original_text",
                    "normalized_start",
                    "normalized_end",
                    "precision",
                    "uncertainty",
                    "semantic_role",
                }
            ),
            "claim": frozenset({"claim_id", "subject_id", "predicate", "stage", "generation"}),
            "fact": frozenset({"fact_id", "subject_id", "predicate", "status"}),
            "evidence": frozenset(
                {
                    "evidence_id",
                    "document_id",
                    "document_version_id",
                    "logical_document_id",
                    "chunk_id",
                    "source_text",
                }
            ),
        }
        return cls(resources=resources)


def validate_logical_ir(ir: LogicalQueryIR, vocabulary: IRVocabulary) -> LogicalQueryIR:
    """Fail closed before any physical planner or engine sees the logical IR."""
    graphs: tuple[LogicalPlanGraph, ...]
    if ir.state == "resolved":
        graphs = (
            LogicalPlanGraph(nodes=ir.nodes, root_ids=ir.root_ids, output=ir.output),  # type: ignore[arg-type]
        )
    else:
        graphs = ir.candidate_plans
    for graph in graphs:
        _validate_graph_semantics(graph, ir.workspace_id, ir, vocabulary)
    return ir


def parse_logical_ir(
    payload: dict[str, object],
    vocabulary: IRVocabulary,
    *,
    allow_safe_repair: bool = True,
) -> LogicalQueryIR:
    candidate = safely_repair_ir_payload(payload) if allow_safe_repair else payload
    try:
        ir = LogicalQueryIR.model_validate(candidate)
    except ValidationError as error:
        error_type = error.errors()[0]["type"]
        raise IRValidationError(f"invalid logical IR schema: {error_type}") from error
    return validate_logical_ir(ir, vocabulary)


def safely_repair_ir_payload(payload: dict[str, object]) -> dict[str, object]:
    """Repair only representation noise that cannot change query meaning."""
    repaired = deepcopy(payload)
    repaired.setdefault("schema_version", "1.0")
    roots = repaired.get("root_ids")
    if isinstance(roots, list):
        repaired["root_ids"] = list(dict.fromkeys(roots))
    nodes = repaired.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("inputs"), list):
                node["inputs"] = list(dict.fromkeys(node["inputs"]))
    candidate_plans = repaired.get("candidate_plans")
    if isinstance(candidate_plans, list):
        for plan in candidate_plans:
            if not isinstance(plan, dict):
                continue
            plan_roots = plan.get("root_ids")
            if isinstance(plan_roots, list):
                plan["root_ids"] = list(dict.fromkeys(plan_roots))
            plan_nodes = plan.get("nodes")
            if isinstance(plan_nodes, list):
                for node in plan_nodes:
                    if isinstance(node, dict) and isinstance(node.get("inputs"), list):
                        node["inputs"] = list(dict.fromkeys(node["inputs"]))
    return repaired


def _validate_graph_semantics(
    graph: LogicalPlanGraph,
    workspace_id: str,
    ir: LogicalQueryIR,
    vocabulary: IRVocabulary,
) -> None:
    nodes = {node.node_id: node for node in graph.nodes}
    for node in graph.nodes:
        if isinstance(node, ScanNode | ResolveNode) and node.workspace_id != workspace_id:
            raise IRValidationError(f"node {node.node_id} crosses the IR workspace boundary")
        if isinstance(node, ScanNode | ResolveNode):
            _require_resource(vocabulary, node.resource)
        for reference in _field_references(node):
            _require_field(vocabulary, reference)
        if isinstance(node, TraverseNode):
            _require_relation(vocabulary, node.relation)
        if isinstance(node, CustomCapabilityNode):
            if node.capability not in vocabulary.custom_capabilities:
                raise IRValidationError(
                    f"custom capability is not declared by the workspace schema: {node.capability}"
                )
        _validate_input_types(node, nodes)
        if isinstance(node, ProjectNode):
            upstream = _upstream_ids(node.inputs, nodes)
            for projected in node.fields:
                if projected.source_node_id not in nodes:
                    raise IRValidationError(
                        f"projection references unknown node: {projected.source_node_id}"
                    )
                if projected.source_node_id not in upstream:
                    raise IRValidationError(
                        f"projection source is not upstream: {projected.source_node_id}"
                    )

    _validate_output(graph, nodes)
    _validate_coverage(graph, ir)


def _require_resource(vocabulary: IRVocabulary, resource: str) -> None:
    if resource not in vocabulary.resources:
        raise IRValidationError(f"resource is not declared by the workspace schema: {resource}")


def _require_field(vocabulary: IRVocabulary, reference: FieldReference) -> None:
    _require_resource(vocabulary, reference.resource)
    if reference.field not in vocabulary.resources[reference.resource]:
        raise IRValidationError(
            f"field is not declared for {reference.resource}: {reference.field}"
        )


def _require_relation(vocabulary: IRVocabulary, reference: RelationReference) -> None:
    declaration = vocabulary.relations.get(reference.relation)
    if declaration is None:
        raise IRValidationError(
            f"relation is not declared by the workspace schema: {reference.relation}"
        )
    if reference.source_resource not in declaration.source_resources:
        raise IRValidationError(
            f"relation {reference.relation} does not accept source {reference.source_resource}"
        )
    if reference.target_resource not in declaration.target_resources:
        raise IRValidationError(
            f"relation {reference.relation} does not accept target {reference.target_resource}"
        )


def _field_references(node: IRNode) -> tuple[FieldReference, ...]:
    if isinstance(node, FilterNode | AggregateNode | RankNode):
        return (node.field if hasattr(node, "field") else node.by,)
    if isinstance(node, DistinctNode | CountNode):
        return node.fields if isinstance(node, DistinctNode) else node.distinct_fields
    if isinstance(node, GroupNode):
        return node.keys
    if isinstance(node, SortNode):
        return tuple(item.field for item in node.keys)
    if isinstance(node, JoinNode):
        return tuple(
            reference
            for condition in node.conditions
            for reference in (condition.left, condition.right)
        )
    if isinstance(node, ProjectNode):
        return tuple(item.source_field for item in node.fields if item.source_field)
    return ()


def _validate_input_types(node: IRNode, nodes: dict[str, IRNode]) -> None:
    input_types = tuple(nodes[node_id].output_type for node_id in node.inputs)
    set_types: set[ValueType] = {
        "entity_set",
        "record_set",
        "document_set",
        "event_set",
        "grouped_set",
        "ranked_set",
        "graph_paths",
    }
    if isinstance(
        node, FilterNode | DistinctNode | SortNode | LimitNode | TemporalConstraintNode
    ):
        if input_types[0] not in set_types or node.output_type != input_types[0]:
            raise IRValidationError(f"node {node.node_id} must preserve its set input type")
    elif isinstance(node, TraverseNode):
        if input_types != ("entity_set",):
            raise IRValidationError("traverse requires one entity_set input")
    elif isinstance(node, JoinNode):
        if any(value not in set_types for value in input_types):
            raise IRValidationError("join requires two set inputs")
    elif isinstance(node, GroupNode):
        if input_types[0] not in set_types:
            raise IRValidationError("group requires a set input")
    elif isinstance(node, AggregateNode | CountNode):
        if input_types[0] not in set_types - {"graph_paths"}:
            raise IRValidationError(f"{node.kind} requires an enumerable set input")
        expected = "record_set" if input_types[0] == "grouped_set" else "scalar"
        if node.output_type != expected:
            raise IRValidationError(f"{node.kind} output type must be {expected}")
    elif isinstance(node, RankNode):
        if input_types[0] not in set_types - {"graph_paths"}:
            raise IRValidationError("rank requires an enumerable set input")
    elif isinstance(node, RetrieveEvidenceNode):
        if input_types[0] not in set_types:
            raise IRValidationError("retrieve_evidence requires a set or graph input")
    elif isinstance(node, CompareNode):
        if any(value not in set_types | {"scalar"} for value in input_types):
            raise IRValidationError("compare requires comparable set or scalar inputs")
    elif isinstance(node, ExistsNode):
        if input_types[0] not in set_types:
            raise IRValidationError("exists requires a set input")
    elif isinstance(node, ProjectNode):
        if input_types[0] in {"boolean", "summary_request", "extension"}:
            raise IRValidationError("project cannot consume this input type")
    elif isinstance(node, SummarizeNode):
        if input_types[0] == "summary_request":
            raise IRValidationError("summarize cannot consume another summary request")


def _validate_output(graph: LogicalPlanGraph, nodes: dict[str, IRNode]) -> None:
    output_types = {nodes[root_id].output_type for root_id in graph.root_ids}
    allowed = {
        "entities": {"entity_set", "ranked_set"},
        "rows": {"record_set", "grouped_set", "ranked_set", "graph_paths"},
        "scalar": {"scalar"},
        "boolean": {"boolean"},
        "comparison": {"comparison_result"},
        "summary": {"summary_request"},
        "evidence": {"evidence_set"},
    }[graph.output.shape]
    if not output_types.issubset(allowed):
        raise IRValidationError(
            f"output shape {graph.output.shape} is incompatible with root types {output_types}"
        )
    if graph.output.fields:
        projected_names = {
            item.name
            for root_id in graph.root_ids
            if isinstance((root := nodes[root_id]), ProjectNode)
            for item in root.fields
        }
        if not set(graph.output.fields).issubset(projected_names):
            raise IRValidationError("output fields must be declared by root projections")


def _upstream_ids(inputs: tuple[str, ...], nodes: dict[str, IRNode]) -> set[str]:
    upstream = set(inputs)
    frontier = list(inputs)
    while frontier:
        node_id = frontier.pop()
        unseen = set(nodes[node_id].inputs) - upstream
        upstream.update(unseen)
        frontier.extend(unseen)
    return upstream


def _validate_coverage(graph: LogicalPlanGraph, ir: LogicalQueryIR) -> None:
    exhaustive_kinds = {"count", "group", "aggregate", "rank"}
    requires_exhaustive = any(node.kind in exhaustive_kinds for node in graph.nodes) or any(
        isinstance(node, ScanNode) and node.population_mode == "exhaustive" for node in graph.nodes
    )
    requires_exhaustive = requires_exhaustive or any(
        isinstance(node, CompareNode) and node.comparison == "populations" for node in graph.nodes
    )
    if requires_exhaustive and ir.coverage.mode != "exhaustive":
        raise IRValidationError("enumeration and aggregation operators require exhaustive coverage")
    if ir.coverage.mode == "exhaustive":
        scans = [node for node in graph.nodes if isinstance(node, ScanNode)]
        if scans and any(node.population_mode != "exhaustive" for node in scans):
            raise IRValidationError("exhaustive plans cannot contain discovery-only scans")
        if not ir.evidence.provenance_chain_required:
            raise IRValidationError("exhaustive plans require provenance chains")
        if ir.evidence.citation_granularity != "exact_span":
            raise IRValidationError("exhaustive plans require exact-span evidence")
