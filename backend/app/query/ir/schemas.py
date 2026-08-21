"""Versioned, typed, provider- and engine-neutral Logical Query IR."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

IR_SCHEMA_VERSION = "1.0"
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")]
ValueType = Literal[
    "entity_set",
    "record_set",
    "document_set",
    "event_set",
    "grouped_set",
    "ranked_set",
    "graph_paths",
    "evidence_set",
    "scalar",
    "boolean",
    "comparison_result",
    "summary_request",
    "extension",
]
PassThroughType = Literal[
    "entity_set",
    "record_set",
    "document_set",
    "event_set",
    "grouped_set",
    "ranked_set",
    "graph_paths",
]


class FieldReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource: Identifier
    field: Identifier


class RelationReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relation: Identifier
    source_resource: Identifier
    target_resource: Identifier


class TemporalPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal[
        "event_date",
        "document_date",
        "mentioned_date",
        "range",
        "before_event",
        "after_event",
        "approximate_date",
        "partial_date",
    ]
    original_text: str = Field(min_length=1, max_length=500)
    normalized_start: str | None = Field(default=None, max_length=32)
    normalized_end: str | None = Field(default=None, max_length=32)
    precision: Literal["day", "month", "year", "season", "decade", "unknown"]
    uncertainty: Literal["certain", "approximate", "unknown"]
    anchor_event: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_shape(self):
        if self.role == "range" and not (self.normalized_start and self.normalized_end):
            raise ValueError("range temporals require both normalized bounds")
        if self.role in {"before_event", "after_event"} and not self.anchor_event:
            raise ValueError("relative temporals require an event anchor")
        if self.role == "approximate_date" and self.uncertainty != "approximate":
            raise ValueError("approximate dates require approximate uncertainty")
        return self


class SortKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FieldReference
    direction: Literal["ascending", "descending"] = "ascending"
    nulls: Literal["first", "last"] = "last"


class ProjectionField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Identifier
    source_node_id: Identifier
    source_field: FieldReference | None = None


class JoinCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left: FieldReference
    right: FieldReference
    comparator: Literal["eq", "not_eq"] = "eq"


class ScanNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["scan"] = "scan"
    node_id: Identifier
    inputs: tuple[()] = ()
    output_type: Literal["entity_set", "record_set", "document_set", "event_set"]
    workspace_id: str = Field(min_length=1, max_length=128)
    resource: Identifier
    population_mode: Literal["discovery", "exhaustive"] = "discovery"


class ResolveNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["resolve"] = "resolve"
    node_id: Identifier
    inputs: tuple[()] = ()
    output_type: Literal["entity_set"] = "entity_set"
    workspace_id: str = Field(min_length=1, max_length=128)
    reference_id: Identifier
    resource: Identifier
    mention: str = Field(min_length=1, max_length=500)
    canonical_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)
    candidate_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def has_resolution_input(self):
        if not (self.canonical_entity_ids or self.candidate_entity_ids):
            raise ValueError("resolve requires canonical or candidate entity identifiers")
        if self.canonical_entity_ids and self.candidate_entity_ids:
            raise ValueError("resolved and candidate entity identifiers cannot be mixed")
        return self


class FilterNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["filter"] = "filter"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: PassThroughType
    field: FieldReference
    comparator: Literal[
        "eq", "not_eq", "lt", "lte", "gt", "gte", "in", "contains", "starts_with", "exists"
    ]
    value: JsonValue = None


class TraverseNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["traverse"] = "traverse"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["entity_set", "graph_paths"]
    relation: RelationReference
    direction: Literal["outgoing", "incoming", "either"] = "outgoing"
    minimum_hops: int = Field(default=1, ge=1, le=10)
    maximum_hops: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def valid_hops(self):
        if self.minimum_hops > self.maximum_hops:
            raise ValueError("minimum_hops cannot exceed maximum_hops")
        return self


class JoinNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["join"] = "join"
    node_id: Identifier
    inputs: tuple[Identifier, Identifier]
    output_type: Literal["record_set"] = "record_set"
    join_type: Literal["inner", "left", "semi", "anti"] = "inner"
    conditions: tuple[JoinCondition, ...] = Field(min_length=1, max_length=20)


class DistinctNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["distinct"] = "distinct"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: PassThroughType
    fields: tuple[FieldReference, ...] = Field(default=(), max_length=20)


class GroupNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["group"] = "group"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["grouped_set"] = "grouped_set"
    keys: tuple[FieldReference, ...] = Field(min_length=1, max_length=20)


class AggregateNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["aggregate"] = "aggregate"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["scalar", "record_set"]
    function: Literal["minimum", "maximum", "sum", "average"]
    field: FieldReference
    alias: Identifier


class CountNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["count"] = "count"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["scalar", "record_set"]
    distinct_fields: tuple[FieldReference, ...] = Field(default=(), max_length=20)
    alias: Identifier = "count"


class RankNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rank"] = "rank"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["ranked_set"] = "ranked_set"
    by: FieldReference
    direction: Literal["ascending", "descending"]
    top_n: int | None = Field(default=None, ge=1, le=10_000)


class SortNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["sort"] = "sort"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: PassThroughType
    keys: tuple[SortKey, ...] = Field(min_length=1, max_length=20)


class LimitNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["limit"] = "limit"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: PassThroughType
    limit: int = Field(ge=1, le=10_000)
    offset: int = Field(default=0, ge=0)


class ProjectNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["project"] = "project"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["record_set"] = "record_set"
    fields: tuple[ProjectionField, ...] = Field(min_length=1, max_length=50)


class TemporalConstraintNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["temporal_constraint"] = "temporal_constraint"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: PassThroughType
    predicates: tuple[TemporalPredicate, ...] = Field(min_length=1, max_length=20)


class RetrieveEvidenceNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["retrieve_evidence"] = "retrieve_evidence"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["evidence_set"] = "evidence_set"
    query_text: str | None = Field(default=None, max_length=2_000)
    maximum_items: int = Field(default=20, ge=1, le=1_000)


class CompareNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["compare"] = "compare"
    node_id: Identifier
    inputs: tuple[Identifier, Identifier]
    output_type: Literal["comparison_result"] = "comparison_result"
    comparison: Literal["values", "populations", "overlap", "difference"]


class ExistsNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["exists"] = "exists"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["boolean"] = "boolean"


class SummarizeNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["summarize"] = "summarize"
    node_id: Identifier
    inputs: tuple[Identifier]
    output_type: Literal["summary_request"] = "summary_request"
    aspects: tuple[str, ...] = Field(default=(), max_length=20)


class CustomCapabilityNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["custom_capability"] = "custom_capability"
    node_id: Identifier
    inputs: tuple[Identifier, ...] = Field(default=(), max_length=20)
    output_type: Literal["extension"] = "extension"
    capability: Identifier
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


IRNode = Annotated[
    ScanNode
    | ResolveNode
    | FilterNode
    | TraverseNode
    | JoinNode
    | DistinctNode
    | GroupNode
    | AggregateNode
    | CountNode
    | RankNode
    | SortNode
    | LimitNode
    | ProjectNode
    | TemporalConstraintNode
    | RetrieveEvidenceNode
    | CompareNode
    | ExistsNode
    | SummarizeNode
    | CustomCapabilityNode,
    Field(discriminator="kind"),
]


class CoverageContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["grounded", "exhaustive", "unspecified"] = "unspecified"
    population_boundary: str | None = Field(default=None, max_length=500)
    same_generation_required: bool = False
    mandatory_projections: tuple[Identifier, ...] = Field(default=(), max_length=20)
    partial_results_allowed: bool = True

    @model_validator(mode="after")
    def valid_exhaustive_contract(self):
        if self.mode == "exhaustive" and not self.population_boundary:
            raise ValueError("exhaustive coverage requires a population boundary")
        if self.mode == "exhaustive" and not self.same_generation_required:
            raise ValueError("exhaustive coverage requires one generation")
        return self


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required: bool = True
    citation_granularity: Literal["none", "source", "exact_span"] = "exact_span"
    provenance_chain_required: bool = True
    minimum_sources: int = Field(default=1, ge=0, le=1_000)
    allow_inference: bool = False

    @model_validator(mode="after")
    def valid_required_evidence(self):
        if self.required and self.citation_granularity == "none":
            raise ValueError("required evidence needs citation granularity")
        if self.required and self.minimum_sources < 1:
            raise ValueError("required evidence needs at least one source")
        return self


class OutputProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    shape: Literal["entities", "rows", "scalar", "boolean", "comparison", "summary", "evidence"]
    fields: tuple[Identifier, ...] = Field(default=(), max_length=50)


def _validate_graph(nodes: tuple[IRNode, ...], root_ids: tuple[str, ...]) -> None:
    node_ids = [node.node_id for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("logical plan node identifiers must be unique")
    known = set(node_ids)
    if not set(root_ids).issubset(known):
        raise ValueError("logical plan roots must reference declared nodes")
    for node in nodes:
        if node.node_id in node.inputs:
            raise ValueError("logical plan nodes cannot depend on themselves")
        if not set(node.inputs).issubset(known):
            raise ValueError(f"node {node.node_id} references an unknown input")
    dependencies = {node.node_id: set(node.inputs) for node in nodes}
    remaining = dict(dependencies)
    while remaining:
        ready = {node_id for node_id, inputs in remaining.items() if not inputs}
        if not ready:
            raise ValueError("logical plan must be acyclic")
        remaining = {
            node_id: inputs - ready
            for node_id, inputs in remaining.items()
            if node_id not in ready
        }
    reachable = set(root_ids)
    frontier = list(root_ids)
    while frontier:
        node_id = frontier.pop()
        inputs = dependencies[node_id]
        unseen = inputs - reachable
        reachable.update(unseen)
        frontier.extend(unseen)
    if reachable != known:
        raise ValueError("every logical plan node must contribute to a root")


class LogicalPlanGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[IRNode, ...] = Field(min_length=1, max_length=500)
    root_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    output: OutputProjection

    @model_validator(mode="after")
    def valid_graph(self):
        _validate_graph(self.nodes, self.root_ids)
        return self


class CandidateLogicalPlan(LogicalPlanGraph):
    label: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1_000)
    confidence: float = Field(ge=0, le=1)


class LogicalQueryIR(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = IR_SCHEMA_VERSION
    workspace_id: str = Field(min_length=1, max_length=128)
    state: Literal["resolved", "ambiguous", "unresolved"]
    nodes: tuple[IRNode, ...] = Field(default=(), max_length=500)
    root_ids: tuple[Identifier, ...] = Field(default=(), max_length=20)
    output: OutputProjection | None = None
    coverage: CoverageContract = Field(default_factory=CoverageContract)
    evidence: EvidenceRequirement = Field(default_factory=EvidenceRequirement)
    candidate_plans: tuple[CandidateLogicalPlan, ...] = Field(default=(), max_length=5)
    issues: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def valid_state_and_graph(self):
        if self.state == "resolved":
            if not self.nodes or not self.root_ids or self.output is None:
                raise ValueError("resolved IR requires a logical plan and output")
            if self.candidate_plans or self.issues:
                raise ValueError("resolved IR cannot retain candidates or unresolved issues")
            _validate_graph(self.nodes, self.root_ids)
        elif self.state == "ambiguous":
            if len(self.candidate_plans) < 2:
                raise ValueError("ambiguous IR requires at least two candidate plans")
            if not self.issues:
                raise ValueError("ambiguous IR requires an ambiguity explanation")
        elif not self.issues:
            raise ValueError("unresolved IR requires at least one issue")
        return self


def is_safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_.-]*", value))
