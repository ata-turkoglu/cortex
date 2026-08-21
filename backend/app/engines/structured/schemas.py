"""Detached canonical inputs and intermediate structured values."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.query.orchestration import CompletenessReport, ExactEvidenceSpan


class CanonicalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1, max_length=256)
    resource: str = Field(min_length=1, max_length=128)
    values: dict[str, JsonValue]
    evidence: tuple[ExactEvidenceSpan, ...] = Field(min_length=1, max_length=10_000)


class CanonicalPopulation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    generation_id: str = Field(min_length=1, max_length=128)
    resource: str = Field(min_length=1, max_length=128)
    boundary: str = Field(min_length=1, max_length=1_000)
    records: tuple[CanonicalRecord, ...] = Field(max_length=100_000)
    candidate_count: int = Field(ge=0)
    unresolved_candidate_ids: tuple[str, ...] = Field(default=(), max_length=100_000)
    safely_enumerable: bool
    ready_projections: tuple[str, ...] = ()

    @model_validator(mode="after")
    def isolated_population(self):
        if any(record.resource != self.resource for record in self.records):
            raise ValueError("population records must share one resource")
        if any(
            evidence.workspace_id != self.workspace_id
            or evidence.generation_id != self.generation_id
            for record in self.records
            for evidence in record.evidence
        ):
            raise ValueError("population evidence must match workspace and generation")
        if len(self.records) + len(self.unresolved_candidate_ids) > self.candidate_count:
            raise ValueError("population members cannot exceed candidate count")
        return self


class StructuredGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    keys: dict[str, JsonValue]
    records: tuple[CanonicalRecord, ...]


class StructuredValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["records", "groups", "scalar", "boolean", "comparison"]
    records: tuple[CanonicalRecord, ...] = ()
    groups: tuple[StructuredGroup, ...] = ()
    scalar: JsonValue = None
    aggregate_function: Literal[
        "count", "distinct_count", "minimum", "maximum", "sum", "average"
    ] | None = None
    completeness: CompletenessReport
