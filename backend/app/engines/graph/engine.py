"""Canonical knowledge graph execution through the Cortex-owned adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.knowledge.graph import (
    CanonicalConflictQueryView,
    CanonicalEntityQueryView,
    CanonicalEvidenceQueryView,
    CanonicalPathQueryView,
)
from app.query.ir.schemas import (
    CustomCapabilityNode,
    ResolveNode,
    TemporalConstraintNode,
    TraverseNode,
)
from app.query.orchestration import (
    ClaimResult,
    CompletenessReport,
    EngineResult,
    EngineTrace,
    EntityResult,
    ExactEvidenceSpan,
    GraphPathResult,
    ProvenanceLink,
    ResultAmbiguity,
    ResultConflict,
)
from app.query.planning import ExecutionStep


class CanonicalGraphReader(Protocol):
    workspace_id: str

    def query_canonical_entities(
        self, generation: str, entity_ids: tuple[str, ...]
    ) -> tuple[CanonicalEntityQueryView, ...]: ...

    def query_canonical_paths(
        self, generation: str, start_entity_ids: tuple[str, ...], relation_type: str,
        direction: str, minimum_hops: int, maximum_hops: int, *, limit: int = 500,
    ) -> tuple[CanonicalPathQueryView, ...]: ...

    def query_event_paths(
        self, generation: str, entity_ids: tuple[str, ...], *,
        normalized_start: str | None = None, normalized_end: str | None = None,
        limit: int = 500,
    ) -> tuple[CanonicalPathQueryView, ...]: ...

    def query_claim_conflicts(
        self, generation: str, subject_ids: tuple[str, ...], *, limit: int = 500,
    ) -> tuple[CanonicalConflictQueryView, ...]: ...

    def query_canonical_artifact_evidence(
        self, generation: str, artifact_ids: tuple[str, ...], *, limit: int = 500,
    ) -> tuple[CanonicalEvidenceQueryView, ...]: ...


@dataclass(frozen=True)
class GraphValue:
    entity_ids: tuple[str, ...] = ()
    paths: tuple[CanonicalPathQueryView, ...] = ()
    artifact_ids: tuple[str, ...] = ()


class GraphExecutionError(ValueError):
    pass


class KnowledgeGraphEngine:
    def __init__(self, workspace_id: str, generation_id: str, reader: CanonicalGraphReader) -> None:
        if reader.workspace_id != workspace_id:
            raise ValueError("graph reader crosses the engine workspace")
        self.workspace_id = workspace_id
        self.generation_id = generation_id
        self.reader = reader

    def execute(
        self, step: ExecutionStep, node, inputs: tuple[GraphValue, ...] = ()
    ) -> tuple[GraphValue, EngineResult]:
        started = perf_counter()
        self._validate(step, node)
        entities: tuple[CanonicalEntityQueryView, ...] = ()
        paths: tuple[CanonicalPathQueryView, ...] = ()
        conflicts: tuple[CanonicalConflictQueryView, ...] = ()
        ambiguity: tuple[ResultAmbiguity, ...] = ()
        if isinstance(node, ResolveNode):
            ids = node.canonical_entity_ids or node.candidate_entity_ids
            entities = self.reader.query_canonical_entities(self.generation_id, ids)
            if len(entities) >= 2 and node.candidate_entity_ids:
                ambiguity = (
                    ResultAmbiguity(
                        ambiguity_id=f"ambiguity-{node.reference_id}",
                        reason="canonical entity resolution remains unresolved",
                        candidate_ids=tuple(item.entity_id for item in entities),
                    ),
                )
            value = GraphValue(entity_ids=tuple(item.entity_id for item in entities))
        elif isinstance(node, TraverseNode):
            source_ids = inputs[0].entity_ids
            paths = self.reader.query_canonical_paths(
                self.generation_id, source_ids, node.relation.relation, node.direction,
                node.minimum_hops, node.maximum_hops,
            )
            value = GraphValue(
                entity_ids=tuple(dict.fromkeys(path.node_ids[-1] for path in paths)), paths=paths,
                artifact_ids=tuple(item for path in paths for item in path.relation_ids),
            )
        elif isinstance(node, TemporalConstraintNode):
            starts = [item.normalized_start for item in node.predicates if item.normalized_start]
            ends = [item.normalized_end for item in node.predicates if item.normalized_end]
            paths = self.reader.query_event_paths(
                self.generation_id, inputs[0].entity_ids,
                normalized_start=min(starts) if starts else None,
                normalized_end=max(ends) if ends else None,
            )
            value = GraphValue(paths=paths, artifact_ids=tuple(
                item for path in paths for item in path.node_ids[1:]))
        elif (
            isinstance(node, CustomCapabilityNode)
            and node.capability == "graph.event_participation"
        ):
            paths = self.reader.query_event_paths(
                self.generation_id, inputs[0].entity_ids
            )
            value = GraphValue(
                paths=paths,
                artifact_ids=tuple(item for path in paths for item in path.node_ids[1:]),
            )
        elif (
            isinstance(node, CustomCapabilityNode)
            and node.capability == "graph.contradiction_analysis"
        ):
            conflicts = self.reader.query_claim_conflicts(self.generation_id, inputs[0].entity_ids)
            value = GraphValue(entity_ids=inputs[0].entity_ids)
        elif (
            isinstance(node, CustomCapabilityNode)
            and node.capability == "graph.provenance_traversal"
        ):
            evidence = self.reader.query_canonical_artifact_evidence(
                self.generation_id, inputs[0].artifact_ids
            )
            value = inputs[0]
            return value, self._result(step, value, (), value.paths, (), (), evidence,
                                       int((perf_counter() - started) * 1_000))
        else:
            raise GraphExecutionError(f"unsupported graph operator: {node.kind}")
        return value, self._result(
            step, value, entities, paths, conflicts, ambiguity, (),
            int((perf_counter() - started) * 1_000),
        )

    def _validate(self, step, node) -> None:
        if step.engine != "knowledge_graph" or step.trace.logical_node_ids != (node.node_id,):
            raise GraphExecutionError("physical step does not match the graph operator")
        if step.readiness.workspace_id != self.workspace_id:
            raise GraphExecutionError("graph step crosses the engine workspace")
        if step.readiness.generation_id != self.generation_id:
            raise GraphExecutionError("graph step uses a different generation")

    def _result(self, step, value, entities, paths, conflicts, ambiguities, direct_evidence,
                duration):
        evidence_views = tuple(direct_evidence) + tuple(
            item for entity in entities for item in entity.evidence
        ) + tuple(item for path in paths for item in path.evidence) + tuple(
            item for conflict in conflicts for item in conflict.evidence
        )
        evidence = _evidence(self.workspace_id, evidence_views)
        valid_ids = {item.evidence_id for item in evidence}
        entity_results = tuple(
            EntityResult(item_id=item.entity_id, entity_id=item.entity_id,
                         entity_type=item.entity_type,
                         values={"display_name": item.display_name, "subtype": item.subtype},
                         evidence_ids=tuple(e.evidence_id for e in item.evidence
                                            if e.evidence_id in valid_ids))
            for item in entities if any(e.evidence_id in valid_ids for e in item.evidence)
        )
        path_results = tuple(
            GraphPathResult(item_id=item.path_id,
                            values={"relation_types": list(item.relation_types)},
                            node_ids=item.node_ids, relation_ids=item.relation_ids,
                            evidence_ids=tuple(e.evidence_id for e in item.evidence
                                               if e.evidence_id in valid_ids))
            for item in paths if any(e.evidence_id in valid_ids for e in item.evidence)
        )
        claims = tuple(
            claim
            for item in conflicts
            for claim in _conflict_claims(item, valid_ids)
        )
        result_conflicts = tuple(
            ResultConflict(conflict_id=f"conflict-{item.left_claim_id}-{item.right_claim_id}",
                           subject=item.subject_id, predicate=item.predicate,
                           left_result_id=item.left_claim_id, right_result_id=item.right_claim_id,
                           reason=item.reason)
            for item in conflicts
        )
        grounded = entity_results + path_results + claims
        completeness = CompletenessReport(
            coverage="grounded", state="unknown", generation_id=self.generation_id,
            confirmed_count=len(grounded),
        )
        return EngineResult(
            result_id=f"result-{step.step_id}", workspace_id=self.workspace_id,
            generation_id=self.generation_id, step_id=step.step_id, engine=step.engine,
            capability=step.capability,
            state="ambiguous" if ambiguities else ("success" if grounded else "unsupported"),
            entities=entity_results, graph_paths=path_results, claims=claims,
            text_evidence=evidence,
            provenance=tuple(ProvenanceLink(result_id=item.item_id,
                                             evidence_ids=item.evidence_ids) for item in grounded),
            completeness=completeness, confidence=0.9 if grounded else 0.0,
            ambiguities=ambiguities, conflicts=result_conflicts,
            trace=EngineTrace(step_id=step.step_id, engine=step.engine,
                              capability=step.capability, duration_ms=duration,
                              counters={"confirmed_count": len(grounded)}),
        )


def _evidence(workspace_id, views):
    unique = {}
    for item in views:
        unique.setdefault(item.evidence_id, ExactEvidenceSpan(
            evidence_id=item.evidence_id, workspace_id=workspace_id,
            document_id=item.document_id, document_version_id=item.document_version_id,
            logical_document_id=item.logical_document_id, chunk_id=item.chunk_id,
            start_offset=item.start_offset, end_offset=item.end_offset,
            source_text=item.source_text, generation_id=item.generation,
            relevance_score=item.confidence, quality_score=item.confidence,
        ))
    return tuple(unique.values())


def _conflict_claims(conflict, valid_ids):
    evidence_ids = tuple(item.evidence_id for item in conflict.evidence
                         if item.evidence_id in valid_ids)
    if not evidence_ids:
        return ()
    return (
        ClaimResult(item_id=conflict.left_claim_id, values={"value": conflict.left_value},
                    evidence_ids=evidence_ids, subject_id=conflict.subject_id,
                    predicate=conflict.predicate, value=conflict.left_value,
                    stage="supported_claim"),
        ClaimResult(item_id=conflict.right_claim_id, values={"value": conflict.right_value},
                    evidence_ids=evidence_ids, subject_id=conflict.subject_id,
                    predicate=conflict.predicate, value=conflict.right_value,
                    stage="supported_claim"),
    )
