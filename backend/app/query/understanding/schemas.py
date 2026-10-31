"""Provider-neutral semantic understanding contract for Query V2."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SEMANTIC_SCHEMA_VERSION = "1.0"
SemanticState = Literal["resolved", "ambiguous", "unresolved"]
SemanticOperator = Literal[
    "describe",
    "resolve_reference",
    "retrieve_evidence",
    "traverse_relation",
    "filter",
    "enumerate",
    "aggregate",
    "compare",
    "order",
    "summarize",
]
StructuredSemanticOperation = Literal["list", "count", "group", "rank", "compare"]
TemporalRole = Literal[
    "event_date",
    "document_date",
    "mentioned_date",
    "range",
    "before_event",
    "after_event",
    "approximate_date",
    "partial_date",
]
ShortText = Annotated[str, Field(min_length=1, max_length=500)]


class SemanticEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1, max_length=80)
    mention: ShortText
    entity_type: ShortText = "unknown"
    reference_kind: Literal["explicit", "follow_up", "conversation_result"] = "explicit"
    resolution: SemanticState = "unresolved"
    canonical_entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    canonical_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)
    display_name: ShortText | None = None
    candidate_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_resolution(self):
        resolved_ids = tuple(
            dict.fromkeys(
                (self.canonical_entity_id,)
                if self.canonical_entity_id
                else self.canonical_entity_ids
            )
        )
        if self.resolution == "resolved" and not resolved_ids:
            raise ValueError("resolved semantic entities require canonical entity IDs")
        if self.resolution != "resolved" and (
            self.canonical_entity_id or self.canonical_entity_ids
        ):
            raise ValueError("unresolved semantic entities cannot carry canonical entity IDs")
        if self.canonical_entity_id and self.canonical_entity_ids:
            raise ValueError("semantic entities use either one canonical ID or a canonical ID set")
        if self.resolution == "ambiguous" and len(self.candidate_entity_ids) < 2:
            raise ValueError("ambiguous semantic entities require at least two candidates")
        return self


class SemanticTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: Literal[
        "entity",
        "person",
        "relation",
        "event",
        "document",
        "property",
        "claim",
        "fact",
        "unknown",
    ]
    reference_id: str | None = Field(default=None, min_length=1, max_length=80)
    description: ShortText


class SemanticRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    predicate: ShortText
    subject_reference_id: str = Field(min_length=1, max_length=80)
    object_reference_id: str | None = Field(default=None, min_length=1, max_length=80)
    direction: Literal["outgoing", "incoming", "either"] = "outgoing"
    target_entity_type: Literal[
        "person", "organization", "location", "asset_property", "entity"
    ] = "entity"


class SemanticTemporalConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: TemporalRole
    original_text: ShortText
    normalized_start: str | None = Field(default=None, max_length=32)
    normalized_end: str | None = Field(default=None, max_length=32)
    precision: Literal["day", "month", "year", "season", "decade", "unknown"]
    uncertainty: Literal["certain", "approximate", "unknown"] = "unknown"
    anchor_event: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def normalize_turkish_dotted_exact_event_date(cls, value):
        if not isinstance(value, dict):
            return value
        if value.get("role") != "event_date" or value.get("precision") != "day":
            return value
        if value.get("uncertainty", "unknown") != "certain":
            return value
        match = re.fullmatch(r"\s*(\d{2})\.(\d{2})\.(\d{4})\s*", value.get("original_text", ""))
        if not match:
            return value
        normalized = f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
        return {**value, "normalized_start": normalized, "normalized_end": normalized}

    @model_validator(mode="after")
    def validate_temporal_shape(self):
        if self.role == "range" and not (self.normalized_start and self.normalized_end):
            raise ValueError("range temporals require normalized_start and normalized_end")
        if self.role in {"before_event", "after_event"} and not self.anchor_event:
            raise ValueError("relative event temporals require anchor_event")
        if self.role == "approximate_date" and self.uncertainty != "approximate":
            raise ValueError("approximate_date requires approximate uncertainty")
        if self.role == "event_date" and self.precision == "day" and self.uncertainty == "certain":
            normalized = self.normalized_start
            if not normalized or normalized != self.normalized_end:
                raise ValueError("exact event_date requires one normalized ISO day")
            try:
                if date.fromisoformat(normalized).isoformat() != normalized:
                    raise ValueError
            except ValueError as error:
                raise ValueError("exact event_date requires a valid ISO day") from error
        return self


class SemanticTypedFilter(BaseModel):
    """A constrained semantic filter; vocabulary validation happens during IR planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: Literal["person", "organization", "location", "asset_property"]
    property: ShortText
    operator: Literal["eq"]
    value: ShortText


class SemanticGovernedField(BaseModel):
    """One advertised canonical property used for governed analytics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: Literal["person", "organization", "location", "asset_property"]
    property: ShortText


class SemanticRelationAggregate(BaseModel):
    """One governed, exhaustive source-to-target distinct-count request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: Literal["person"]
    relation: ShortText
    target_type: Literal["asset_property"]
    distinct_target_identity: Literal["entity_id"] = "entity_id"
    count_alias: Literal["property_count"] = "property_count"
    direction: Literal["ascending", "descending"]


class SemanticProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["person.surname", "structured_operation"]
    source: Literal["provider", "governed_query_completion"]


class InterpretationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: ShortText
    explanation: ShortText
    entities: tuple[SemanticEntity, ...] = Field(default=(), max_length=20)
    targets: tuple[SemanticTarget, ...] = Field(default=(), max_length=20)
    relations: tuple[SemanticRelation, ...] = Field(default=(), max_length=20)
    temporal_constraints: tuple[SemanticTemporalConstraint, ...] = Field(default=(), max_length=20)
    typed_filters: tuple[SemanticTypedFilter, ...] = Field(default=(), max_length=20)
    structured_operation: StructuredSemanticOperation | None = None
    group_by: SemanticGovernedField | None = None
    rank_direction: Literal["ascending", "descending"] | None = None
    relation_aggregate: SemanticRelationAggregate | None = None
    operators: tuple[SemanticOperator, ...] = Field(default=(), max_length=20)
    confidence: float = Field(ge=0, le=1)


class SemanticUnderstanding(BaseModel):
    """Meaning only: this contract contains no physical route or engine selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = SEMANTIC_SCHEMA_VERSION
    state: SemanticState
    entities: tuple[SemanticEntity, ...] = Field(default=(), max_length=20)
    targets: tuple[SemanticTarget, ...] = Field(default=(), max_length=20)
    relations: tuple[SemanticRelation, ...] = Field(default=(), max_length=20)
    temporal_constraints: tuple[SemanticTemporalConstraint, ...] = Field(default=(), max_length=20)
    typed_filters: tuple[SemanticTypedFilter, ...] = Field(default=(), max_length=20)
    structured_operation: StructuredSemanticOperation | None = None
    group_by: SemanticGovernedField | None = None
    rank_direction: Literal["ascending", "descending"] | None = None
    relation_aggregate: SemanticRelationAggregate | None = None
    operators: tuple[SemanticOperator, ...] = Field(default=(), max_length=20)
    uses_temporal_focus: bool = False
    coverage: Literal["relevant_evidence", "corpus_required", "unspecified"] = "unspecified"
    candidates: tuple[InterpretationCandidate, ...] = Field(default=(), max_length=5)
    ambiguity_reasons: tuple[ShortText, ...] = Field(default=(), max_length=10)
    unresolved_questions: tuple[ShortText, ...] = Field(default=(), max_length=10)
    semantic_provenance: tuple[SemanticProvenance, ...] = Field(default=(), max_length=10)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_state(self):
        if self.state == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous understanding requires at least two candidates")
        grounded_unresolved_retrieval = (
            self.coverage == "relevant_evidence"
            and self.structured_operation is None
            and not self.typed_filters
            and not self.relations
            and not self.temporal_constraints
            and {"describe", "retrieve_evidence"}.issubset(self.operators)
        )
        if self.state == "unresolved" and not (
            self.unresolved_questions or grounded_unresolved_retrieval
        ):
            raise ValueError("unresolved understanding requires a clarification question")
        if self.state == "resolved" and (self.candidates or self.unresolved_questions):
            raise ValueError("resolved understanding cannot retain candidates or questions")
        if self.structured_operation in {"list", "count"} and not (
            self.typed_filters or any(item.target_type == "person" for item in self.targets)
        ):
            raise ValueError(
                "structured list/count operations require a typed filter or Person target"
            )
        if self.structured_operation in {"group", "rank"} and not (
            self.group_by or self.relation_aggregate
        ):
            raise ValueError("structured group/rank operations require a governed group field")
        if self.structured_operation == "rank" and not (
            self.rank_direction or self.relation_aggregate
        ):
            raise ValueError("structured rank operations require a direction")
        if self.structured_operation == "compare" and len(self.typed_filters) != 2:
            raise ValueError("structured compare operations require exactly two typed filters")
        if self.relation_aggregate and self.coverage != "corpus_required":
            raise ValueError("relation aggregate requires corpus_required coverage")
        entity_refs = {item.reference_id for item in self.entities}
        referenced = {
            ref
            for relation in self.relations
            for ref in (relation.subject_reference_id, relation.object_reference_id)
            if ref
        }
        if not referenced.issubset(entity_refs):
            raise ValueError("relations must reference declared semantic entities")
        return self
