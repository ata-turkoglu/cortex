"""Schema-constrained semantic planner with bounded repair and tier escalation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import ValidationError

from ...core.config import Settings, get_settings
from ...providers.base import GeneratedText
from ...providers.openai import OpenAIProvider
from ..context import ConversationContext
from .schemas import SemanticUnderstanding

PlannerTier = Literal["simple", "standard", "complex"]
_TIERS: tuple[PlannerTier, ...] = ("simple", "standard", "complex")


class StructuredPlannerProvider(Protocol):
    async def generate_structured(
        self,
        model: str,
        instructions: str,
        input_text: str,
        *,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> GeneratedText: ...


@dataclass(frozen=True)
class PlannerModel:
    provider: str
    model: str


@dataclass(frozen=True)
class PlannerAttempt:
    tier: PlannerTier
    provider: str
    model: str
    repaired: bool
    state: str | None


@dataclass(frozen=True)
class SemanticPlannerResult:
    understanding: SemanticUnderstanding
    selected_tier: PlannerTier
    attempts: tuple[PlannerAttempt, ...]
    generated: GeneratedText

    @property
    def escalated(self) -> bool:
        return len({item.tier for item in self.attempts}) > 1


class SemanticPlannerOutputError(RuntimeError):
    pass


def planner_models(settings: Settings | None = None) -> dict[PlannerTier, PlannerModel]:
    source = settings or get_settings()
    return {
        "simple": PlannerModel(
            source.semantic_planner_simple_provider, source.semantic_planner_simple_model
        ),
        "standard": PlannerModel(
            source.semantic_planner_standard_provider, source.semantic_planner_standard_model
        ),
        "complex": PlannerModel(
            source.semantic_planner_complex_provider, source.semantic_planner_complex_model
        ),
    }


def select_planner_tier(query: str, context: ConversationContext) -> PlannerTier:
    """Choose prompt depth from shape only; semantic interpretation remains model-owned."""
    if context.state.candidate_references or len(query) > 500:
        return "complex"
    if len(query) > 160 or len(context.history) > 6:
        return "standard"
    return "simple"


class SemanticPlannerAdapter:
    def __init__(
        self,
        *,
        models: dict[PlannerTier, PlannerModel] | None = None,
        providers: dict[str, StructuredPlannerProvider] | None = None,
        repair_attempts: int | None = None,
        escalation_enabled: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        settings = get_settings()
        self.models = models or planner_models(settings)
        self.providers = providers or {"openai": OpenAIProvider()}
        self.repair_attempts = (
            settings.semantic_planner_repair_attempts
            if repair_attempts is None
            else repair_attempts
        )
        self.escalation_enabled = (
            settings.semantic_planner_escalation_enabled
            if escalation_enabled is None
            else escalation_enabled
        )
        self.confidence_threshold = (
            settings.semantic_planner_confidence_threshold
            if confidence_threshold is None
            else confidence_threshold
        )

    async def plan(
        self,
        query: str,
        context: ConversationContext,
        *,
        preferred_tier: PlannerTier | None = None,
        workspace_briefing: dict[str, object] | None = None,
    ) -> SemanticPlannerResult:
        if not query.strip():
            raise ValueError("query must not be empty")
        initial_tier = preferred_tier or select_planner_tier(query, context)
        tiers = _TIERS[_TIERS.index(initial_tier) :]
        attempts: list[PlannerAttempt] = []
        last_error: ValidationError | None = None
        last_result: tuple[SemanticUnderstanding, GeneratedText, PlannerTier] | None = None
        schema = _strict_json_schema(SemanticUnderstanding.model_json_schema())
        input_text = json.dumps(
            {
                "query": query,
                "conversation_context": context.model_dump(mode="json"),
                "workspace_briefing": workspace_briefing,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        for tier in tiers:
            assignment = self.models[tier]
            provider = self.providers.get(assignment.provider)
            if provider is None:
                raise RuntimeError(
                    f"semantic planner provider is not available: {assignment.provider}"
                )
            instructions = _instructions(tier)
            for repair_index in range(self.repair_attempts + 1):
                generated = await provider.generate_structured(
                    assignment.model,
                    instructions,
                    input_text,
                    schema_name="semantic_understanding_v1",
                    json_schema=schema,
                )
                try:
                    understanding = SemanticUnderstanding.model_validate_json(generated.text)
                except ValidationError as error:
                    last_error = error
                    attempts.append(
                        PlannerAttempt(
                            tier,
                            assignment.provider,
                            assignment.model,
                            repair_index > 0,
                            None,
                        )
                    )
                    instructions = _repair_instructions(tier, error)
                    continue
                attempts.append(
                    PlannerAttempt(
                        tier,
                        assignment.provider,
                        assignment.model,
                        repair_index > 0,
                        understanding.state,
                    )
                )
                last_result = (understanding, generated, tier)
                if not self._needs_escalation(understanding) or tier == "complex":
                    return SemanticPlannerResult(
                        understanding=understanding,
                        selected_tier=tier,
                        attempts=tuple(attempts),
                        generated=generated,
                    )
                break
            if not self.escalation_enabled:
                break

        if last_result:
            understanding, generated, tier = last_result
            return SemanticPlannerResult(
                understanding=understanding,
                selected_tier=tier,
                attempts=tuple(attempts),
                generated=generated,
            )
        detail = str(last_error).splitlines()[0] if last_error else "empty planner result"
        raise SemanticPlannerOutputError(f"semantic planner output was invalid: {detail}")

    def _needs_escalation(self, understanding: SemanticUnderstanding) -> bool:
        return self.escalation_enabled and (
            understanding.state != "resolved"
            or understanding.confidence < self.confidence_threshold
        )


def _instructions(tier: PlannerTier) -> str:
    return (
        "Interpret the user's meaning using only the supplied conversation context. "
        "The optional workspace briefing is a bounded identity catalogue. Use an entity ID only "
        "when it exactly identifies the mentioned entity; never invent an ID or corpus fact. "
        "Return the strict schema. Keep ambiguity and unresolved references explicit. "
        "Distinguish event, document, mentioned, range, relative, approximate, and partial dates. "
        "Do not choose execution engines or physical routes. "
        f"Planner depth: {tier}."
    )


def _repair_instructions(tier: PlannerTier, error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
        for item in error.errors()[:5]
    )
    return (
        _instructions(tier) + f" The prior output failed schema validation: {problems}. Repair it."
    )


def _strict_json_schema(value: object) -> object:
    """Convert Pydantic defaults into an all-fields-required strict API schema."""
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {
        key: _strict_json_schema(item)
        for key, item in value.items()
        if key not in {"default", "title"}
    }
    properties = result.get("properties")
    if isinstance(properties, dict):
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result
