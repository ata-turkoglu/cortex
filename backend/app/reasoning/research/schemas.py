"""Versioned durable contracts for multi-query workspace research."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...query.ir.schemas import LogicalQueryIR
from ...query.orchestration.schemas import ReasoningPackage
from ...query.planning.schemas import PhysicalExecutionPlan

RESEARCH_SCHEMA_VERSION = "1.0"


class ResearchSubquery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subquery_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=128)
    question: str = Field(min_length=1, max_length=4_000)
    purpose: str = Field(min_length=1, max_length=2_000)
    depends_on: tuple[str, ...] = Field(default=(), max_length=100)
    state: Literal["planned", "ready", "executing", "collected", "failed"] = "planned"
    logical_ir: LogicalQueryIR | None = None
    execution_plan: PhysicalExecutionPlan | None = None
    package: ReasoningPackage | None = None
    issue: str | None = Field(default=None, max_length=2_000)


class ResearchDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subqueries: tuple[ResearchSubquery, ...] = Field(min_length=1, max_length=100)
    reasoning_strategy: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def valid_dag(self):
        ids = [item.subquery_id for item in self.subqueries]
        if len(ids) != len(set(ids)):
            raise ValueError("research subquery IDs must be unique")
        known: set[str] = set()
        for item in self.subqueries:
            if set(item.depends_on) - known:
                raise ValueError("research dependencies must reference earlier subqueries")
            known.add(item.subquery_id)
        return self


class CrossSourceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=10_000)
    kind: Literal["finding", "inference", "disagreement"]
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    source_subquery_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)


class ResearchCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = RESEARCH_SCHEMA_VERSION
    run_id: str
    workspace_id: str
    goal: str = Field(min_length=1, max_length=20_000)
    generation_id: str | None = None
    state: Literal[
        "created", "decomposing", "planned", "executing", "reasoning",
        "ready", "partial", "unsupported", "failed",
    ] = "created"
    decomposition: ResearchDecomposition | None = None
    claims: tuple[CrossSourceClaim, ...] = Field(default=(), max_length=10_000)
    issues: tuple[str, ...] = Field(default=(), max_length=1_000)
    validation_state: Literal["pending", "grounded", "partial", "failed"] = "pending"

    @model_validator(mode="after")
    def isolated_and_grounded(self):
        subqueries = self.decomposition.subqueries if self.decomposition else ()
        ids = {item.subquery_id for item in subqueries}
        evidence_ids: set[str] = set()
        for item in subqueries:
            if item.logical_ir and item.logical_ir.workspace_id != self.workspace_id:
                raise ValueError("research IR cannot cross the run workspace")
            if item.execution_plan and item.execution_plan.workspace_id != self.workspace_id:
                raise ValueError("research plan cannot cross the run workspace")
            if item.package:
                if item.package.workspace_id != self.workspace_id:
                    raise ValueError("research evidence cannot cross the run workspace")
                if self.generation_id and item.package.generation_id != self.generation_id:
                    raise ValueError("research evidence cannot mix generations")
                evidence_ids.update(citation.evidence_id for citation in item.package.citations)
        for claim in self.claims:
            if not set(claim.source_subquery_ids) <= ids:
                raise ValueError("research claims must reference declared subqueries")
            if not set(claim.evidence_ids) <= evidence_ids:
                raise ValueError("research claims must retain collected evidence lineage")
        if self.state == "ready" and (
            not self.claims or self.validation_state != "grounded"
            or any(item.state != "collected" for item in subqueries)
        ):
            raise ValueError("ready research requires collected subqueries and grounded claims")
        return self


class ResearchPlanner(Protocol):
    def decompose(self, goal: str, workspace_id: str) -> ResearchDecomposition: ...
