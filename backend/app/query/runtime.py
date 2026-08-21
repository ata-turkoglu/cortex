"""Detached V2 query preparation from context through a physical execution plan.

The caller must load conversation context and readiness in short SQLite work, close that work,
then await this service. This boundary does not execute engines, write messages, or mutate the
runtime activation pointer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .briefing import WorkspaceBriefing, resolve_workspace_entities
from .context import ConversationContext
from .ir import IRVocabulary, LogicalQueryIR, lower_semantic_understanding
from .planning import PhysicalExecutionPlan, PlanningReadinessSnapshot, plan_execution
from .understanding import SemanticPlannerResult


class SemanticPlanner(Protocol):
    async def plan(
        self,
        query: str,
        context: ConversationContext,
        *,
        workspace_briefing: dict[str, object] | None = None,
    ) -> SemanticPlannerResult: ...


@dataclass(frozen=True)
class PreparedQuery:
    """One detached semantic-to-physical V2 preparation result."""

    semantic: SemanticPlannerResult
    logical_ir: LogicalQueryIR
    physical_plan: PhysicalExecutionPlan


class QueryV2PreparationService:
    """Compose semantic planning, IR lowering, validation, and physical planning."""

    def __init__(self, planner: SemanticPlanner) -> None:
        self.planner = planner

    async def prepare(
        self,
        query: str,
        context: ConversationContext,
        vocabulary: IRVocabulary,
        readiness: PlanningReadinessSnapshot,
        briefing: WorkspaceBriefing | None = None,
    ) -> PreparedQuery:
        if context.workspace_id != readiness.workspace_id:
            raise ValueError("conversation context and readiness cross workspace boundaries")
        if briefing and (
            briefing.workspace_id != context.workspace_id
            or briefing.generation_id != readiness.active_generation_id
        ):
            raise ValueError("workspace briefing does not match the active planning generation")
        semantic = await self.planner.plan(
            query,
            context,
            workspace_briefing=briefing.planner_context() if briefing else None,
        )
        if briefing:
            semantic = semantic.__class__(
                understanding=resolve_workspace_entities(semantic.understanding, briefing),
                selected_tier=semantic.selected_tier,
                attempts=semantic.attempts,
                generated=semantic.generated,
            )
        logical_ir = lower_semantic_understanding(semantic.understanding, context.workspace_id)
        physical_plan = plan_execution(logical_ir, vocabulary, readiness)
        return PreparedQuery(
            semantic=semantic,
            logical_ir=logical_ir,
            physical_plan=physical_plan,
        )
