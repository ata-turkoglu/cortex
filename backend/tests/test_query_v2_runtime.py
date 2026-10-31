import asyncio

import pytest

from app.providers.base import GeneratedText
from app.query.briefing import WorkspaceBriefing, WorkspaceEntityCandidate
from app.query.context import ConversationContext
from app.query.ir import IRVocabulary
from app.query.planning import DEFAULT_CAPABILITIES, CapabilityReadiness, PlanningReadinessSnapshot
from app.query.runtime import QueryV2PreparationService
from app.query.understanding import SemanticEntity, SemanticPlannerResult, SemanticUnderstanding


class StubPlanner:
    def __init__(self):
        self.briefing = None

    async def plan(self, query, context, *, workspace_briefing=None):
        self.briefing = workspace_briefing
        return SemanticPlannerResult(
            understanding=SemanticUnderstanding(
                state="resolved",
                entities=(
                    SemanticEntity(
                        reference_id="person-1",
                        mention="Ada",
                        entity_type="person",
                        resolution="resolved",
                        canonical_entity_id="entity-1",
                    ),
                ),
                confidence=1.0,
            ),
            selected_tier="simple",
            attempts=(),
            generated=GeneratedText(text="{}"),
        )


def _readiness(workspace_id="workspace-a"):
    return PlanningReadinessSnapshot(
        workspace_id=workspace_id,
        active_generation_id="generation-a",
        capabilities=tuple(
            CapabilityReadiness(
                workspace_id=workspace_id,
                engine=capability.engine,
                capability=capability.capability,
                state="ready",
                generation_id="generation-a" if capability.requires_generation else None,
            )
            for capability in DEFAULT_CAPABILITIES
        ),
    )


def test_preparation_composes_semantics_ir_and_physical_plan_without_persistence():
    planner = StubPlanner()
    prepared = asyncio.run(
        QueryV2PreparationService(planner).prepare(
            "Who is Ada?",
            ConversationContext(
                workspace_id="workspace-a", conversation_id="conversation-a", revision=0
            ),
            IRVocabulary.core(),
            _readiness(),
            WorkspaceBriefing(
                workspace_id="workspace-a",
                generation_id="generation-a",
                entities=(WorkspaceEntityCandidate("entity-1", "person", "Ada"),),
            ),
        )
    )

    assert prepared.semantic.understanding.state == "resolved"
    assert prepared.logical_ir.workspace_id == "workspace-a"
    assert prepared.physical_plan.state == "ready"
    assert planner.briefing["canonical_entities"][0]["entity_id"] == "entity-1"


def test_preparation_rejects_cross_workspace_detached_inputs():
    service = QueryV2PreparationService(StubPlanner())

    with pytest.raises(ValueError, match="cross workspace"):
        asyncio.run(
            service.prepare(
                "Who is Ada?",
                ConversationContext(
                    workspace_id="workspace-a", conversation_id="conversation-a", revision=0
                ),
                IRVocabulary.core(),
                _readiness("workspace-b"),
            )
        )


def test_preparation_rejects_a_briefing_from_a_different_generation():
    with pytest.raises(ValueError, match="active planning generation"):
        asyncio.run(
            QueryV2PreparationService(StubPlanner()).prepare(
                "Who is Ada?",
                ConversationContext(
                    workspace_id="workspace-a", conversation_id="conversation-a", revision=0
                ),
                IRVocabulary.core(),
                _readiness(),
                WorkspaceBriefing(
                    workspace_id="workspace-a",
                    generation_id="generation-b",
                    entities=(),
                ),
            )
        )
