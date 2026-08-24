"""Deterministic lowering from validated semantic meaning into Logical Query IR."""

from __future__ import annotations

from dataclasses import dataclass

from ..understanding import (
    SemanticEntity,
    SemanticGovernedField,
    SemanticTypedFilter,
    SemanticUnderstanding,
)
from .schemas import (
    CandidateLogicalPlan,
    CompareNode,
    CountNode,
    CoverageContract,
    DistinctNode,
    EventSetNode,
    EvidenceRequirement,
    FilterNode,
    GroupNode,
    IRNode,
    LogicalQueryIR,
    OutputProjection,
    RankNode,
    ResolveNode,
    RetrieveEvidenceNode,
    ScanNode,
    SummarizeNode,
    TemporalConstraintNode,
    TemporalPredicate,
    TraverseNode,
)


@dataclass(frozen=True)
class _GraphResult:
    nodes: tuple[IRNode, ...]
    root_ids: tuple[str, ...]
    output: OutputProjection


def lower_semantic_understanding(
    understanding: SemanticUnderstanding,
    workspace_id: str,
) -> LogicalQueryIR:
    """Lower meaning only; no provider, storage, route, or engine decision occurs here."""
    coverage = _coverage(understanding.coverage)
    evidence = EvidenceRequirement()
    if understanding.state == "unresolved":
        return LogicalQueryIR(
            workspace_id=workspace_id,
            state="unresolved",
            coverage=coverage,
            evidence=evidence,
            issues=understanding.unresolved_questions,
        )
    if understanding.state == "ambiguous":
        plans: list[CandidateLogicalPlan] = []
        issues: list[str] = list(understanding.ambiguity_reasons)
        for candidate in understanding.candidates:
            try:
                graph = _lower_graph(
                    candidate.entities,
                    candidate.targets,
                    candidate.relations,
                    candidate.temporal_constraints,
                    candidate.typed_filters,
                    candidate.structured_operation,
                    candidate.group_by,
                    candidate.rank_direction,
                    candidate.operators,
                    workspace_id,
                    coverage,
                )
            except ValueError as error:
                issues.append(f"{candidate.label}: {error}")
                continue
            plans.append(
                CandidateLogicalPlan(
                    label=candidate.label,
                    explanation=candidate.explanation,
                    confidence=candidate.confidence,
                    nodes=graph.nodes,
                    root_ids=graph.root_ids,
                    output=graph.output,
                )
            )
        if len(plans) < 2:
            return LogicalQueryIR(
                workspace_id=workspace_id,
                state="unresolved",
                coverage=coverage,
                evidence=evidence,
                issues=tuple(issues or ["candidate interpretations could not be lowered safely"]),
            )
        return LogicalQueryIR(
            workspace_id=workspace_id,
            state="ambiguous",
            coverage=coverage,
            evidence=evidence,
            candidate_plans=tuple(plans),
            issues=tuple(issues or ["multiple semantic interpretations remain"]),
        )

    try:
        graph = _lower_graph(
            understanding.entities,
            understanding.targets,
            understanding.relations,
            understanding.temporal_constraints,
            understanding.typed_filters,
            understanding.structured_operation,
            understanding.group_by,
            understanding.rank_direction,
            understanding.operators,
            workspace_id,
            coverage,
        )
    except ValueError as error:
        return LogicalQueryIR(
            workspace_id=workspace_id,
            state="unresolved",
            coverage=coverage,
            evidence=evidence,
            issues=(str(error),),
        )
    return LogicalQueryIR(
        workspace_id=workspace_id,
        state="resolved",
        nodes=graph.nodes,
        root_ids=graph.root_ids,
        output=graph.output,
        coverage=coverage,
        evidence=evidence,
    )


def _lower_graph(
    entities,
    targets,
    relations,
    temporals,
    typed_filters: tuple[SemanticTypedFilter, ...],
    structured_operation: str | None,
    group_by: SemanticGovernedField | None,
    rank_direction: str | None,
    operators,
    workspace_id: str,
    coverage: CoverageContract,
) -> _GraphResult:
    nodes: list[IRNode] = []
    roots: list[str] = []
    reference_nodes: dict[str, str] = {}
    reference_resources: dict[str, str] = {}
    for ordinal, entity in enumerate(entities, start=1):
        node = _resolve_node(entity, ordinal, workspace_id)
        nodes.append(node)
        roots.append(node.node_id)
        reference_nodes[entity.reference_id] = node.node_id
        reference_resources[entity.reference_id] = node.resource

    for ordinal, target in enumerate(targets, start=1):
        if target.reference_id and target.reference_id in reference_nodes:
            continue
        if target.target_type == "event":
            node = EventSetNode(node_id=f"event_set_{ordinal}")
            nodes.append(node)
            roots.append(node.node_id)
            continue
        resource, output_type = _target_resource(target.target_type)
        if resource is None:
            raise ValueError(
                f"semantic target is not lowerable without clarification: {target.description}"
            )
        node = ScanNode(
            node_id=f"scan_{ordinal}",
            output_type=output_type,
            workspace_id=workspace_id,
            resource=resource,
            population_mode=("exhaustive" if coverage.mode == "exhaustive" else "discovery"),
        )
        nodes.append(node)
        roots.append(node.node_id)

    if not roots and any(item.role == "event_date" for item in temporals):
        node = EventSetNode(node_id="event_set_1")
        nodes.append(node)
        roots.append(node.node_id)

    for ordinal, relation in enumerate(relations, start=1):
        subject_node = reference_nodes.get(relation.subject_reference_id)
        if subject_node is None:
            raise ValueError(f"relation subject is unresolved: {relation.subject_reference_id}")
        source_resource = reference_resources[relation.subject_reference_id]
        target_resource = reference_resources.get(
            relation.object_reference_id or "", relation.target_entity_type
        )
        node = TraverseNode(
            node_id=f"traverse_{ordinal}",
            inputs=(subject_node,),
            output_type="entity_set",
            relation={
                "relation": relation.predicate,
                "source_resource": source_resource,
                "target_resource": target_resource,
            },
            direction=relation.direction,
        )
        nodes.append(node)
        roots = [item for item in roots if item != subject_node]
        roots.append(node.node_id)

    if temporals:
        predicates = tuple(
            TemporalPredicate(
                role=item.role,
                original_text=item.original_text,
                normalized_start=item.normalized_start,
                normalized_end=item.normalized_end,
                precision=item.precision,
                uncertainty=item.uncertainty,
                anchor_event=item.anchor_event,
            )
            for item in temporals
        )
        roots = _map_set_roots(
            nodes,
            roots,
            lambda root, output, ordinal: TemporalConstraintNode(
                node_id=f"temporal_{ordinal}",
                inputs=(root,),
                output_type=output,
                predicates=predicates,
            ),
        )

    for ordinal, typed_filter in enumerate(typed_filters, start=1):
        matching_roots = []
        for root in roots:
            reference = next(
                (ref for ref, node_id in reference_nodes.items() if node_id == root), ""
            )
            if reference_resources.get(reference) == typed_filter.target_type:
                matching_roots.append(root)
        if not matching_roots:
            # A filter may introduce its own governed canonical population.
            node = ScanNode(
                node_id=f"filter_scan_{ordinal}",
                output_type="entity_set",
                workspace_id=workspace_id,
                resource=typed_filter.target_type,
                population_mode=("exhaustive" if coverage.mode == "exhaustive" else "discovery"),
            )
            nodes.append(node)
            roots.append(node.node_id)
            matching_roots = [node.node_id]
        for root in matching_roots:
            node = FilterNode(
                node_id=f"filter_{ordinal}_{root}",
                inputs=(root,),
                output_type="entity_set",
                field={"resource": typed_filter.target_type, "field": typed_filter.property},
                comparator=typed_filter.operator,
                value=typed_filter.value,
            )
            nodes.append(node)
            roots[roots.index(root)] = node.node_id

    if structured_operation in {"group", "rank"} and group_by and not roots:
        node = ScanNode(
            node_id="analytics_scan_1",
            output_type="entity_set",
            workspace_id=workspace_id,
            resource=group_by.target_type,
            population_mode="exhaustive",
        )
        nodes.append(node)
        roots.append(node.node_id)

    if not roots:
        raise ValueError("semantic understanding contains no lowerable target")

    if structured_operation:
        if coverage.mode != "exhaustive":
            raise ValueError("structured analytics require corpus_required coverage")
        if structured_operation == "compare":
            if len(roots) != 2:
                raise ValueError("structured compare requires two canonical populations")
            node = CompareNode(
                node_id="compare_1", inputs=(roots[0], roots[1]), comparison="populations"
            )
            nodes.append(node)
            roots = [node.node_id]
        elif len(roots) != 1:
            raise ValueError("structured analytics require one canonical population")
        if structured_operation == "count":
            node = CountNode(node_id="count_1", inputs=(roots[0],), output_type="scalar")
            nodes.append(node)
            roots = [node.node_id]
        elif structured_operation in {"group", "rank"}:
            assert group_by is not None
            node = GroupNode(
                node_id="group_1",
                inputs=(roots[0],),
                keys=({"resource": group_by.target_type, "field": group_by.property},),
            )
            nodes.append(node)
            roots = [node.node_id]
            if structured_operation == "rank":
                node = RankNode(
                    node_id="rank_1",
                    inputs=(roots[0],),
                    by={"resource": group_by.target_type, "field": group_by.property},
                    direction=rank_direction or "descending",
                )
                nodes.append(node)
                roots = [node.node_id]

    operator_set = set(operators)
    unsupported = operator_set & {"filter", "aggregate", "order"}
    if unsupported:
        raise ValueError(
            "semantic operators require typed arguments before lowering: "
            + ", ".join(sorted(unsupported))
        )
    if "enumerate" in operator_set and not structured_operation:
        roots = _map_set_roots(
            nodes,
            roots,
            lambda root, output, ordinal: DistinctNode(
                node_id=f"distinct_{ordinal}", inputs=(root,), output_type=output
            ),
        )
    if "compare" in operator_set and structured_operation != "compare":
        if len(roots) != 2:
            raise ValueError("compare requires exactly two lowerable semantic targets")
        node = CompareNode(
            node_id="compare_1",
            inputs=(roots[0], roots[1]),
            comparison=("populations" if coverage.mode == "exhaustive" else "values"),
        )
        nodes.append(node)
        roots = [node.node_id]
    wants_evidence = "retrieve_evidence" in operator_set or "describe" in operator_set
    if wants_evidence:
        roots = _map_evidence_roots(nodes, roots)
    if "summarize" in operator_set or "describe" in operator_set:
        if len(roots) != 1:
            raise ValueError("summarize requires one converged logical input")
        node = SummarizeNode(node_id="summarize_1", inputs=(roots[0],))
        nodes.append(node)
        roots = [node.node_id]

    output_by_id = {node.node_id: node.output_type for node in nodes}
    output_type = output_by_id[roots[0]]
    if any(output_by_id[item] != output_type for item in roots):
        raise ValueError("multiple roots require compatible output types")
    return _GraphResult(tuple(nodes), tuple(roots), _output_projection(output_type))


def _resolve_node(entity: SemanticEntity, ordinal: int, workspace_id: str) -> ResolveNode:
    if entity.resolution == "resolved" and (
        entity.canonical_entity_id or entity.canonical_entity_ids
    ):
        canonical_ids = entity.canonical_entity_ids or (entity.canonical_entity_id,)
        candidates: tuple[str, ...] = ()
    elif entity.resolution == "ambiguous" and entity.candidate_entity_ids:
        canonical_ids = ()
        candidates = entity.candidate_entity_ids
    else:
        raise ValueError(f"entity reference is unresolved: {entity.mention}")
    return ResolveNode(
        node_id=f"resolve_{ordinal}",
        workspace_id=workspace_id,
        reference_id=entity.reference_id,
        resource=_entity_resource(entity.entity_type),
        mention=entity.mention,
        canonical_entity_ids=canonical_ids,
        candidate_entity_ids=candidates,
    )


def _map_set_roots(nodes, roots, factory):
    output_by_id = {node.node_id: node.output_type for node in nodes}
    mapped = []
    allowed = {
        "entity_set",
        "record_set",
        "document_set",
        "event_set",
        "grouped_set",
        "ranked_set",
        "graph_paths",
    }
    for ordinal, root in enumerate(roots, start=1):
        output = output_by_id[root]
        if output not in allowed:
            raise ValueError("set operator cannot consume a scalar or composed result")
        node = factory(root, output, ordinal)
        nodes.append(node)
        mapped.append(node.node_id)
    return mapped


def _map_evidence_roots(nodes, roots):
    output_by_id = {node.node_id: node.output_type for node in nodes}
    if len(roots) != 1:
        raise ValueError("evidence retrieval requires one converged logical target")
    if output_by_id[roots[0]] not in {
        "entity_set",
        "record_set",
        "document_set",
        "event_set",
        "grouped_set",
        "ranked_set",
        "graph_paths",
    }:
        raise ValueError("evidence retrieval requires a set or graph target")
    node = RetrieveEvidenceNode(node_id="evidence_1", inputs=(roots[0],))
    nodes.append(node)
    return [node.node_id]


def _entity_resource(entity_type: str) -> str:
    return {
        "person": "person",
        "organization": "organization",
        "location": "location",
        "place": "location",
        "property": "asset_property",
        "asset_property": "asset_property",
        "unknown": "entity",
    }.get(entity_type, entity_type)


def _target_resource(target_type: str):
    return {
        "relation": ("entity", "entity_set"),
        "event": ("event", "event_set"),
        "document": ("document", "document_set"),
        "property": ("asset_property", "entity_set"),
        "claim": ("claim", "record_set"),
        "fact": ("fact", "record_set"),
    }.get(target_type, (None, None))


def _coverage(value: str) -> CoverageContract:
    if value == "corpus_required":
        return CoverageContract(
            mode="exhaustive",
            population_boundary="active workspace corpus constrained by the semantic targets",
            same_generation_required=True,
            partial_results_allowed=False,
        )
    if value == "relevant_evidence":
        return CoverageContract(mode="grounded")
    return CoverageContract()


def _output_projection(output_type: str) -> OutputProjection:
    shape = {
        "entity_set": "entities",
        "record_set": "rows",
        "document_set": "rows",
        "event_set": "rows",
        "grouped_set": "rows",
        "ranked_set": "rows",
        "graph_paths": "rows",
        "evidence_set": "evidence",
        "scalar": "scalar",
        "boolean": "boolean",
        "comparison_result": "comparison",
        "summary_request": "summary",
    }.get(output_type)
    if shape is None:
        raise ValueError(f"logical output type is not projectable: {output_type}")
    return OutputProjection(shape=shape)
