"""Typed, engine-neutral physical execution-plan contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXECUTION_PLAN_SCHEMA_VERSION = "1.0"
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")]
CoverageLevel = Literal["grounded", "exhaustive"]
PlanValueType = Literal[
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
    "evidence_package",
]


class CapabilityDeclaration(BaseModel):
    """One independently selectable engine capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: Identifier
    capability: Identifier
    input_types: tuple[PlanValueType, ...] = ()
    output_types: tuple[PlanValueType, ...] = Field(min_length=1)
    maximum_coverage: CoverageLevel
    requires_generation: bool = True
    required_projections: tuple[Identifier, ...] = ()
    correctness: int = Field(ge=0, le=100)
    evidence_quality: int = Field(ge=0, le=100)
    coverage_quality: int = Field(ge=0, le=100)
    reasoning_quality: int = Field(ge=0, le=100)
    latency: int = Field(ge=0, le=100)
    cost: int = Field(ge=0, le=100)


class CapabilityReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    engine: Identifier
    capability: Identifier
    state: Literal["ready", "stale", "unavailable"]
    generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    ready_projections: tuple[Identifier, ...] = ()
    detail: str | None = Field(default=None, max_length=500)


class PlanningReadinessSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    active_generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    capabilities: tuple[CapabilityReadiness, ...]

    @model_validator(mode="after")
    def isolated_workspace(self):
        if any(item.workspace_id != self.workspace_id for item in self.capabilities):
            raise ValueError("readiness entries cannot cross the snapshot workspace boundary")
        keys = [(item.engine, item.capability) for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("readiness entries must be unique by engine and capability")
        return self


class ReadinessRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    generation_id: str | None = Field(default=None, min_length=1, max_length=128)
    projections: tuple[Identifier, ...] = ()
    state: Literal["ready"] = "ready"


class FallbackOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: Identifier
    capability: Identifier
    preserves_correctness: bool
    preserves_coverage: bool


class FailurePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["fail_closed", "return_partial"]
    fallback_options: tuple[FallbackOption, ...] = ()


class PlanTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_node_ids: tuple[Identifier, ...]
    selection_reason: str = Field(min_length=1, max_length=1_000)
    optimization_order: tuple[str, ...] = (
        "correctness",
        "evidence_quality",
        "coverage",
        "reasoning_quality",
        "latency",
        "cost",
    )


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: Identifier
    engine: Identifier
    capability: Identifier
    dependencies: tuple[Identifier, ...] = ()
    input_types: tuple[PlanValueType, ...] = ()
    output_type: PlanValueType
    coverage_expectation: CoverageLevel
    readiness: ReadinessRequirement
    failure_policy: FailurePolicy
    trace: PlanTrace


def _validate_step_graph(steps: tuple[ExecutionStep, ...], root_step_ids: tuple[str, ...]) -> None:
    step_ids = [step.step_id for step in steps]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("execution step identifiers must be unique")
    known = set(step_ids)
    if not set(root_step_ids).issubset(known):
        raise ValueError("execution roots must reference declared steps")
    dependencies = {step.step_id: set(step.dependencies) for step in steps}
    if any(not values.issubset(known) for values in dependencies.values()):
        raise ValueError("execution steps cannot reference unknown dependencies")
    remaining = dict(dependencies)
    while remaining:
        ready = {step_id for step_id, values in remaining.items() if not values}
        if not ready:
            raise ValueError("execution plan must be acyclic")
        remaining = {
            step_id: values - ready
            for step_id, values in remaining.items()
            if step_id not in ready
        }
    reachable = set(root_step_ids)
    frontier = list(root_step_ids)
    while frontier:
        unseen = dependencies[frontier.pop()] - reachable
        reachable.update(unseen)
        frontier.extend(unseen)
    if reachable != known:
        raise ValueError("every execution step must contribute to a root")


class ExecutionPlanGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = Field(default=None, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    steps: tuple[ExecutionStep, ...] = Field(min_length=1, max_length=1_000)
    root_step_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_graph(self):
        _validate_step_graph(self.steps, self.root_step_ids)
        return self


class PhysicalExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = EXECUTION_PLAN_SCHEMA_VERSION
    workspace_id: str = Field(min_length=1, max_length=128)
    state: Literal["ready", "ambiguous", "unresolved", "unsupported"]
    graph: ExecutionPlanGraph | None = None
    candidate_plans: tuple[ExecutionPlanGraph, ...] = Field(default=(), max_length=5)
    issues: tuple[str, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def valid_state(self):
        if self.state == "ready" and (self.graph is None or self.candidate_plans or self.issues):
            raise ValueError("ready plans require exactly one graph and no issues")
        if self.state == "ambiguous" and (len(self.candidate_plans) < 2 or not self.issues):
            raise ValueError("ambiguous plans require candidates and issues")
        if self.state in {"unresolved", "unsupported"} and not self.issues:
            raise ValueError(f"{self.state} plans require issues")
        if self.state in {"unresolved", "unsupported"} and (
            self.graph is not None or self.candidate_plans
        ):
            raise ValueError(f"{self.state} plans cannot contain executable graphs")
        return self
