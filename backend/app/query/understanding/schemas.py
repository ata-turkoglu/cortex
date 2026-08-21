"""Provider-neutral semantic understanding contract for Query V2."""

from __future__ import annotations

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
    reference_kind: Literal["explicit", "follow_up"] = "explicit"
    resolution: SemanticState = "unresolved"
    canonical_entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: ShortText | None = None
    candidate_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.resolution == "resolved" and not self.canonical_entity_id:
            raise ValueError("resolved semantic entities require canonical_entity_id")
        if self.resolution != "resolved" and self.canonical_entity_id:
            raise ValueError("unresolved semantic entities cannot carry canonical_entity_id")
        if self.resolution == "ambiguous" and len(self.candidate_entity_ids) < 2:
            raise ValueError("ambiguous semantic entities require at least two candidates")
        return self


class SemanticTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: Literal[
        "entity", "relation", "event", "document", "property", "claim", "fact", "unknown"
    ]
    reference_id: str | None = Field(default=None, min_length=1, max_length=80)
    description: ShortText


class SemanticRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    predicate: ShortText
    subject_reference_id: str = Field(min_length=1, max_length=80)
    object_reference_id: str | None = Field(default=None, min_length=1, max_length=80)
    direction: Literal["outgoing", "incoming", "either"] = "outgoing"


class SemanticTemporalConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: TemporalRole
    original_text: ShortText
    normalized_start: str | None = Field(default=None, max_length=32)
    normalized_end: str | None = Field(default=None, max_length=32)
    precision: Literal["day", "month", "year", "season", "decade", "unknown"]
    uncertainty: Literal["certain", "approximate", "unknown"] = "unknown"
    anchor_event: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_temporal_shape(self):
        if self.role == "range" and not (self.normalized_start and self.normalized_end):
            raise ValueError("range temporals require normalized_start and normalized_end")
        if self.role in {"before_event", "after_event"} and not self.anchor_event:
            raise ValueError("relative event temporals require anchor_event")
        if self.role == "approximate_date" and self.uncertainty != "approximate":
            raise ValueError("approximate_date requires approximate uncertainty")
        return self


class InterpretationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: ShortText
    explanation: ShortText
    entities: tuple[SemanticEntity, ...] = Field(default=(), max_length=20)
    targets: tuple[SemanticTarget, ...] = Field(default=(), max_length=20)
    relations: tuple[SemanticRelation, ...] = Field(default=(), max_length=20)
    temporal_constraints: tuple[SemanticTemporalConstraint, ...] = Field(default=(), max_length=20)
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
    operators: tuple[SemanticOperator, ...] = Field(default=(), max_length=20)
    uses_temporal_focus: bool = False
    coverage: Literal["relevant_evidence", "corpus_required", "unspecified"] = "unspecified"
    candidates: tuple[InterpretationCandidate, ...] = Field(default=(), max_length=5)
    ambiguity_reasons: tuple[ShortText, ...] = Field(default=(), max_length=10)
    unresolved_questions: tuple[ShortText, ...] = Field(default=(), max_length=10)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_state(self):
        if self.state == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous understanding requires at least two candidates")
        if self.state == "unresolved" and not self.unresolved_questions:
            raise ValueError("unresolved understanding requires a clarification question")
        if self.state == "resolved" and (self.candidates or self.unresolved_questions):
            raise ValueError("resolved understanding cannot retain candidates or questions")
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
