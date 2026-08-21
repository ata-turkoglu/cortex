"""Typed, conversation-local state for Query V2."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTEXT_SCHEMA_VERSION = "1.0"
ShortText = Annotated[str, Field(min_length=1, max_length=500)]


class ContextEntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mention: ShortText
    entity_type: ShortText = "unknown"
    resolution: Literal["resolved", "ambiguous", "unresolved"]
    canonical_entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: ShortText | None = None
    candidate_entity_ids: tuple[str, ...] = Field(default=(), max_length=20)
    source_message_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.resolution == "resolved" and not self.canonical_entity_id:
            raise ValueError("resolved references require canonical_entity_id")
        if self.resolution != "resolved" and self.canonical_entity_id:
            raise ValueError("only resolved references may carry canonical_entity_id")
        if self.resolution == "ambiguous" and len(self.candidate_entity_ids) < 2:
            raise ValueError("ambiguous references require at least two candidates")
        return self


class ContextTemporalFocus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_text: ShortText
    semantic_role: Literal[
        "event_date",
        "document_date",
        "mentioned_date",
        "range",
        "before_event",
        "after_event",
        "approximate_date",
        "partial_date",
    ] = "mentioned_date"
    normalized_start: str | None = Field(default=None, max_length=32)
    normalized_end: str | None = Field(default=None, max_length=32)
    precision: Literal["day", "month", "year", "season", "decade", "unknown"] = "unknown"
    uncertainty: Literal["certain", "approximate", "unknown"] = "unknown"
    anchor_event: str | None = Field(default=None, max_length=500)
    source_message_id: str | None = Field(default=None, min_length=1, max_length=36)


class ContextConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ShortText
    value: ShortText
    source_message_id: str | None = Field(default=None, min_length=1, max_length=36)


class ContextAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: ShortText
    status: Literal["active", "rejected"] = "active"
    source_message_id: str | None = Field(default=None, min_length=1, max_length=36)


class ConversationContextState(BaseModel):
    """Persisted state only; message history remains in the existing message table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = CONTEXT_SCHEMA_VERSION
    resolved_entities: tuple[ContextEntityReference, ...] = Field(default=(), max_length=20)
    candidate_references: tuple[ContextEntityReference, ...] = Field(default=(), max_length=20)
    temporal_focus: tuple[ContextTemporalFocus, ...] = Field(default=(), max_length=10)
    explicit_constraints: tuple[ContextConstraint, ...] = Field(default=(), max_length=20)
    assumptions: tuple[ContextAssumption, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_reference_buckets(self):
        if any(item.resolution != "resolved" for item in self.resolved_entities):
            raise ValueError("resolved_entities may contain only resolved references")
        if any(item.resolution == "resolved" for item in self.candidate_references):
            raise ValueError("candidate_references may not contain resolved references")
        return self


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class ConversationContext(BaseModel):
    """Planner-facing detached snapshot safe to use during external calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    conversation_id: str
    revision: int = Field(ge=0)
    summary: str | None = None
    history: tuple[ConversationTurn, ...] = ()
    state: ConversationContextState = Field(default_factory=ConversationContextState)
