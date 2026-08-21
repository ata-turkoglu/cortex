"""Typed contracts for engine output and the common Result & Evidence boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

ENGINE_RESULT_SCHEMA_VERSION = "1.0"
REASONING_PACKAGE_SCHEMA_VERSION = "1.0"
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")]


class ExactEvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    document_version_id: str = Field(min_length=1, max_length=128)
    logical_document_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=128)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    source_text: str = Field(min_length=1)
    generation_id: str = Field(min_length=1, max_length=128)
    relevance_score: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("evidence offsets must be ordered and non-empty")
        if self.end_offset - self.start_offset != len(self.source_text):
            raise ValueError("source text length must exactly match its offsets")
        return self


class GroundedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1, max_length=256)
    values: dict[str, JsonValue]
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)


class EntityResult(GroundedItem):
    entity_id: str = Field(min_length=1, max_length=128)
    entity_type: Identifier


class GraphPathResult(GroundedItem):
    node_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    relation_ids: tuple[str, ...] = Field(default=(), max_length=99)

    @model_validator(mode="after")
    def connected_path(self):
        if self.relation_ids and len(self.relation_ids) != len(self.node_ids) - 1:
            raise ValueError("graph paths require one relation between adjacent nodes")
        return self


class AggregateResult(GroundedItem):
    function: Literal["count", "distinct_count", "minimum", "maximum", "sum", "average"]
    value: JsonValue
    population_count: int | None = Field(default=None, ge=0)


class GraphRAGFinding(GroundedItem):
    mode: Literal["local", "global", "drift", "community_context"]
    text: str = Field(min_length=1, max_length=100_000)


class ClaimResult(GroundedItem):
    subject_id: str = Field(min_length=1, max_length=128)
    predicate: Identifier
    value: JsonValue
    stage: Literal["extracted_claim", "supported_claim", "verified_fact"]


class ProvenanceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: str = Field(min_length=1, max_length=256)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    lineage: tuple[Identifier, ...] = Field(default=(), max_length=20)


class ResultAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ambiguity_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2_000)
    candidate_ids: tuple[str, ...] = Field(min_length=2, max_length=20)


class ResultConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conflict_id: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=256)
    predicate: str = Field(min_length=1, max_length=256)
    left_result_id: str = Field(min_length=1, max_length=256)
    right_result_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=2_000)


class EngineFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: Identifier
    engine: Identifier
    capability: Identifier
    reason: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False


class CompletenessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: Literal["grounded", "exhaustive"]
    state: Literal["complete", "partial", "unknown"]
    boundary: str | None = Field(default=None, max_length=1_000)
    generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    candidate_count: int | None = Field(default=None, ge=0)
    processed_count: int | None = Field(default=None, ge=0)
    confirmed_count: int | None = Field(default=None, ge=0)
    unresolved_candidate_ids: tuple[str, ...] = Field(default=(), max_length=100_000)
    not_safely_enumerable: bool = False
    ready_projections: tuple[Identifier, ...] = ()
    missing_projections: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def truthful_complete_state(self):
        if self.state != "complete":
            return self
        if self.coverage != "exhaustive" or not self.boundary or not self.generation_id:
            raise ValueError("complete results require an exhaustive boundary and generation")
        if self.candidate_count is None or self.processed_count != self.candidate_count:
            raise ValueError("complete results require all candidates to be processed")
        if self.missing_projections:
            raise ValueError("complete results cannot have missing projections")
        if self.not_safely_enumerable or self.unresolved_candidate_ids:
            raise ValueError("complete results cannot retain unsafe or unresolved populations")
        return self


class EngineTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: Identifier
    engine: Identifier
    capability: Identifier
    duration_ms: int = Field(ge=0)
    counters: dict[str, int] = Field(default_factory=dict)
    warnings: tuple[str, ...] = Field(default=(), max_length=100)


class EngineResult(BaseModel):
    """Engine-owned findings only; final answer prose is intentionally impossible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = ENGINE_RESULT_SCHEMA_VERSION
    result_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    step_id: Identifier
    engine: Identifier
    capability: Identifier
    state: Literal["success", "partial", "failed", "ambiguous", "unsupported"]
    structured_rows: tuple[GroundedItem, ...] = Field(default=(), max_length=10_000)
    entities: tuple[EntityResult, ...] = Field(default=(), max_length=10_000)
    graph_paths: tuple[GraphPathResult, ...] = Field(default=(), max_length=10_000)
    aggregates: tuple[AggregateResult, ...] = Field(default=(), max_length=10_000)
    text_evidence: tuple[ExactEvidenceSpan, ...] = Field(default=(), max_length=10_000)
    graphrag_findings: tuple[GraphRAGFinding, ...] = Field(default=(), max_length=10_000)
    claims: tuple[ClaimResult, ...] = Field(default=(), max_length=10_000)
    provenance: tuple[ProvenanceLink, ...] = Field(default=(), max_length=20_000)
    completeness: CompletenessReport
    confidence: float = Field(ge=0, le=1)
    ambiguities: tuple[ResultAmbiguity, ...] = Field(default=(), max_length=100)
    conflicts: tuple[ResultConflict, ...] = Field(default=(), max_length=1_000)
    failures: tuple[EngineFailure, ...] = Field(default=(), max_length=100)
    trace: EngineTrace

    @model_validator(mode="after")
    def coherent_envelope(self):
        if self.step_id != self.trace.step_id:
            raise ValueError("engine result and trace step identifiers must match")
        if self.engine != self.trace.engine or self.capability != self.trace.capability:
            raise ValueError("engine result and trace capability identities must match")
        if any(item.workspace_id != self.workspace_id for item in self.text_evidence):
            raise ValueError("engine evidence cannot cross the result workspace boundary")
        if self.generation_id and any(
            item.generation_id != self.generation_id for item in self.text_evidence
        ):
            raise ValueError("engine evidence cannot mix result generations")
        payload_count = sum(
            len(items)
            for items in (
                self.structured_rows,
                self.entities,
                self.graph_paths,
                self.aggregates,
                self.text_evidence,
                self.graphrag_findings,
                self.claims,
            )
        )
        if self.state == "failed" and (payload_count or not self.failures):
            raise ValueError("failed engine results contain failures and no result payload")
        if self.state == "success" and self.failures:
            raise ValueError("successful engine results cannot contain failures")
        if self.state == "ambiguous" and not self.ambiguities:
            raise ValueError("ambiguous engine results require ambiguity details")
        grounded_items = (
            self.structured_rows
            + self.entities
            + self.graph_paths
            + self.aggregates
            + self.graphrag_findings
            + self.claims
        )
        evidence_ids = {item.evidence_id for item in self.text_evidence}
        if any(not set(item.evidence_ids).issubset(evidence_ids) for item in grounded_items):
            raise ValueError("grounded engine items cannot reference undeclared evidence")
        result_ids = {item.item_id for item in grounded_items}
        if any(link.result_id not in result_ids for link in self.provenance):
            raise ValueError("provenance links must reference a declared grounded result")
        if any(not set(link.evidence_ids).issubset(evidence_ids) for link in self.provenance):
            raise ValueError("provenance links cannot reference undeclared evidence")
        return self


class TrustedSource(BaseModel):
    """Detached source snapshot loaded before reconciliation starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    document_version_id: str = Field(min_length=1, max_length=128)
    logical_document_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=128)
    content: str
    generation_id: str = Field(min_length=1, max_length=128)
    citation_label: str = Field(min_length=1, max_length=500)


class ExpectedResultStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: Identifier
    engine: Identifier
    capability: Identifier
    required: bool = True
    generation_required: bool = True


class ReconciliationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    coverage: Literal["grounded", "exhaustive"]
    generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    boundary: str | None = Field(default=None, max_length=1_000)
    expected_steps: tuple[ExpectedResultStep, ...] = Field(min_length=1, max_length=1_000)
    mandatory_projections: tuple[Identifier, ...] = ()
    minimum_sources: int = Field(default=1, ge=0, le=1_000)
    partial_results_allowed: bool = True

    @model_validator(mode="after")
    def exhaustive_requirements(self):
        if self.coverage == "exhaustive" and (not self.generation_id or not self.boundary):
            raise ValueError("exhaustive reconciliation requires a generation and boundary")
        step_ids = [step.step_id for step in self.expected_steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("expected reconciliation steps must be unique")
        return self


class MaterializedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(min_length=1, max_length=128)
    evidence_id: str = Field(min_length=1, max_length=128)
    document_id: str
    document_version_id: str
    logical_document_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    source_text: str
    label: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    supporting_step_ids: tuple[Identifier, ...] = Field(min_length=1)


class ReasoningPackage(BaseModel):
    """Trustworthy findings for reasoning or Answer Engine handoff; never final prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = REASONING_PACKAGE_SCHEMA_VERSION
    workspace_id: str
    generation_id: str | None = None
    state: Literal["grounded", "corpus_complete", "partial", "unsupported", "ambiguous"]
    structured_rows: tuple[GroundedItem, ...] = ()
    entities: tuple[EntityResult, ...] = ()
    graph_paths: tuple[GraphPathResult, ...] = ()
    aggregates: tuple[AggregateResult, ...] = ()
    graphrag_findings: tuple[GraphRAGFinding, ...] = ()
    claims: tuple[ClaimResult, ...] = ()
    citations: tuple[MaterializedCitation, ...] = ()
    provenance: tuple[ProvenanceLink, ...] = ()
    completeness: CompletenessReport
    confidence: float = Field(ge=0, le=1)
    ambiguities: tuple[ResultAmbiguity, ...] = ()
    conflicts: tuple[ResultConflict, ...] = ()
    failures: tuple[EngineFailure, ...] = ()
    traces: tuple[EngineTrace, ...] = ()
    issues: tuple[str, ...] = ()
