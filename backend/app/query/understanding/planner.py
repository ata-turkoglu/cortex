"""Schema-constrained semantic planner with bounded repair and tier escalation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from pydantic import ValidationError

from ...core.config import Settings, get_settings
from ...providers.base import GeneratedText
from ...providers.openai import OpenAIProvider
from ..context import ConversationContext
from .schemas import SemanticUnderstanding

PlannerTier = Literal["simple", "standard", "complex"]
_TIERS: tuple[PlannerTier, ...] = ("simple", "standard", "complex")
_ANALYTIC_TERMS = (
    "en fazla",
    "en az",
    "sırala",
    "siral",
    "sıral",
    "ranking",
    "rank",
    "highest",
    "lowest",
    "sort",
    "order by",
    "group by",
)
_COUNT_TERMS = ("sayısı", "sayisi", "adet", "kaç", "kac", "count", "number of")
_ENUMERATION_TERMS = ("listele", "list", "her biri", "each", "tüm", "tum", "all")


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
    normalized = query.casefold()
    is_analytic = any(term in normalized for term in _ANALYTIC_TERMS) or (
        any(term in normalized for term in _COUNT_TERMS)
        and any(term in normalized for term in _ENUMERATION_TERMS)
    )
    if len(query) > 160 or len(context.history) > 6 or is_analytic:
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
                    understanding = _normalize_exact_temporals(understanding)
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
        "For an exhaustive count of properties per person, emit a relation_aggregate with "
        "source_type=person, relation=owns, target_type=asset_property, distinct_target_identity="
        "entity_id, count_alias=property_count, and the requested direction. Such a response "
        "also requires structured_operation=rank, coverage=corpus_required, one typed_filters "
        "entry for the governed Person field (for example property=surname, operator=eq), and "
        "rank_direction may be omitted because relation_aggregate carries it. Do not emit a "
        "separate group_by for this relation aggregate. For a field-filtered population, do not "
        "emit SemanticEntity or SemanticRelation records: emit one target_type=entity target for "
        "Person, the typed filter, and the relation_aggregate only. A surname is a population "
        "filter, not a request to resolve one canonical person. Operators are optional semantic "
        "hints; "
        "do not use filter, aggregate, or order unless their corresponding typed fields are "
        "present. "
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


def _normalize_exact_temporals(understanding: SemanticUnderstanding) -> SemanticUnderstanding:
    """Normalize deterministic Turkish dotted dates after semantic role selection."""
    constraints = tuple(_normalize_temporal(item) for item in understanding.temporal_constraints)
    return understanding.model_copy(update={"temporal_constraints": constraints})


def _normalize_temporal(item):
    if item.role != "event_date" or item.precision != "day" or item.uncertainty != "certain":
        return item
    match = re.fullmatch(r"\s*(\d{2})\.(\d{2})\.(\d{4})\s*", item.original_text)
    if not match:
        return item
    normalized = f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    try:
        if date.fromisoformat(normalized).isoformat() != normalized:
            raise ValueError
    except ValueError as error:
        raise ValueError("exact event_date requires a valid calendar day") from error
    return item.model_copy(update={"normalized_start": normalized, "normalized_end": normalized})
