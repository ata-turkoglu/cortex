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
from .schemas import SemanticTarget, SemanticUnderstanding

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
    # The provider response, kept so every billed call can be recorded as usage.
    generated: GeneratedText | None = None


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
    def __init__(self, message: str, attempts: tuple[PlannerAttempt, ...] = ()) -> None:
        super().__init__(message)
        # Failed attempts were still billed; callers record their usage.
        self.attempts = attempts


class GovernedSemanticConflict(ValueError):
    """The provider contradicts an explicit governed fact in the raw user query."""


_SURNAME_POPULATION_PATTERNS = (
    re.compile(
        r"\b(?P<surname>[^\W\d_]{2,})\s+soyadl[\u0131i]"
        r"(?:\s+(?:ka\u00e7|kac)(?:\s+tane)?)?\s+ki[\u015fs]i",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<surname>[^\W\d_]{2,})\s+soyad[\u0131i]ndaki\s+ki[\u015fs]i",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsoyad[\u0131i]\s+(?P<surname>[^\W\d_]{2,})\s+olan\s+ki[\u015fs]i",
        re.IGNORECASE,
    ),
)
_EXPLICIT_LIST_PATTERN = re.compile(r"\bki[\u015fs]i(?:leri)?\s+listele\b", re.IGNORECASE)
_EXPLICIT_COUNT_PATTERN = re.compile(
    r"\b(?:ka\u00e7|kac)(?:\s+tane)?\s+ki[\u015fs]i\b|\btoplam\s+(?:ka\u00e7|kac)\b|\bsay[\u0131i]s[\u0131i]\b",
    re.IGNORECASE,
)
_ACTIVE_CORPUS_PERSON_LIST_PATTERN = re.compile(
    r"\b(?:etkin|aktif)\s+belgelerde\s+ge[çc]en\s+"
    r"(?:t[üu]m\s+|b[üu]t[üu]n\s+)?ki[şs]i(?:leri)?\s+listele\b",
    re.IGNORECASE,
)


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
        deterministic = _deterministic_active_corpus_person_list(query)
        if deterministic is not None:
            generated = GeneratedText(text=deterministic.model_dump_json())
            return SemanticPlannerResult(
                understanding=deterministic,
                selected_tier="simple",
                attempts=(
                    PlannerAttempt(
                        "simple",
                        "deterministic",
                        "governed-person-inventory-v1",
                        False,
                        deterministic.state,
                    ),
                ),
                generated=generated,
            )
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
                    payload = json.loads(generated.text)
                    if not isinstance(payload, dict):
                        raise ValueError("semantic planner output must be an object")
                    payload = complete_governed_semantics(payload, query)
                    understanding = SemanticUnderstanding.model_validate(payload)
                    understanding = _normalize_semantic_output(understanding, query)
                except (ValidationError, ValueError, json.JSONDecodeError) as error:
                    last_error = error
                    attempts.append(
                        PlannerAttempt(
                            tier,
                            assignment.provider,
                            assignment.model,
                            repair_index > 0,
                            None,
                            generated,
                        )
                    )
                    if isinstance(error, GovernedSemanticConflict):
                        raise SemanticPlannerOutputError(str(error), tuple(attempts)) from error
                    instructions = _repair_instructions(tier, error)
                    continue
                attempts.append(
                    PlannerAttempt(
                        tier,
                        assignment.provider,
                        assignment.model,
                        repair_index > 0,
                        understanding.state,
                        generated,
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
        raise SemanticPlannerOutputError(
            f"semantic planner output was invalid: {detail}", tuple(attempts)
        )

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
        "For an ordinary grounded descriptive or evidence request about a named entity, an "
        "unresolved canonical identity does not make the request unsupported: retain the "
        "unresolved entity and use describe and/or retrieve_evidence with "
        "coverage=relevant_evidence. Set state=unresolved with an empty unresolved_questions "
        "list for this retrieval-only shape; do not ask the user to resolve identity first. "
        "Do not add typed filters, relations, aggregates, ordering, "
        "or an exhaustive operation unless the user actually requested that canonical work. "
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
        "hints. For an explicit request to enumerate or count every Person in the active corpus, "
        "emit target_type=person, structured_operation=list or count, coverage=corpus_required, "
        "and the enumerate or aggregate operator as applicable. Do not add a typed filter when "
        "the user did not state one. "
        "do not use filter, aggregate, or order unless their corresponding typed fields are "
        "present. "
        f"Planner depth: {tier}."
    )


def _repair_instructions(tier: PlannerTier, error: Exception) -> str:
    problems = (
        "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
            for item in error.errors()[:5]
        )
        if isinstance(error, ValidationError)
        else str(error)
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


def _normalize_semantic_output(
    understanding: SemanticUnderstanding, query: str
) -> SemanticUnderstanding:
    """Repair representation omissions without inventing query fields or relations."""
    constraints = tuple(_normalize_temporal(item) for item in understanding.temporal_constraints)
    structured_operation = understanding.structured_operation
    # A count is fully determined when the provider has already supplied the
    # governed population filter and aggregate hint, while the user's wording
    # explicitly asks for a cardinality. This only fills the typed operation
    # discriminator; arbitrary aggregates remain unsupported.
    if (
        structured_operation is None
        and "aggregate" in understanding.operators
        and understanding.typed_filters
        and not understanding.group_by
        and understanding.relation_aggregate is None
        and _has_explicit_count_semantics(query)
    ):
        structured_operation = "count"
    return understanding.model_copy(
        update={"temporal_constraints": constraints, "structured_operation": structured_operation}
    )


def _has_explicit_count_semantics(query: str) -> bool:
    normalized = query.casefold()
    return any(term in normalized for term in _COUNT_TERMS) or bool(
        re.search(r"\bhow many\b", normalized)
    )


def _deterministic_active_corpus_person_list(query: str) -> SemanticUnderstanding | None:
    """Recognize the narrow, unambiguous active-document Person inventory.

    This is a governed semantic rule, not a retrieval fallback: it has an exact
    corpus boundary and no named entity, filter, relation, ordering, or metric.
    Keeping it local avoids making a clear bounded inventory unavailable when a
    remote semantic provider is temporarily rate-limited.
    """
    if not _ACTIVE_CORPUS_PERSON_LIST_PATTERN.search(query):
        return None
    normalized = query.casefold()
    if any(term in normalized for term in (*_ANALYTIC_TERMS, *_COUNT_TERMS)):
        return None
    return SemanticUnderstanding(
        state="resolved",
        targets=(
            SemanticTarget(
                target_type="person",
                description="people mentioned in the active documents",
            ),
        ),
        structured_operation="list",
        operators=("enumerate",),
        coverage="corpus_required",
        semantic_provenance=(
            {
                "field": "structured_operation",
                "source": "governed_query_completion",
            },
        ),
        confidence=1.0,
    )


def complete_governed_semantics(payload: dict[str, object], query: str) -> dict[str, object]:
    """Add only explicit governed facts absent from a provider semantic payload.

    This is deliberately not an intent router: it needs a provider payload and
    only fills the supported Person surname population and its explicit list or
    count operation. Relations and metrics remain provider-owned.
    """
    completed = _complete_explicit_person_inventory(payload, query)
    provenance = list(completed.get("semantic_provenance") or [])
    surname = _explicit_surname_population(query)
    if surname is None:
        return completed
    typed_filters = list(completed.get("typed_filters") or [])
    person_surname_filters = [
        item
        for item in typed_filters
        if isinstance(item, dict)
        and item.get("target_type") == "person"
        and item.get("property") == "surname"
    ]
    conflicting_target = any(
        isinstance(item, dict) and item.get("target_type") not in {"person", None}
        for item in typed_filters
    )
    if conflicting_target:
        raise GovernedSemanticConflict(
            "provider governed filter conflicts with explicit Person surname scope"
        )
    if person_surname_filters:
        if any(
            str(item.get("value", "")).casefold() != surname.casefold()
            for item in person_surname_filters
        ):
            raise GovernedSemanticConflict(
                "provider surname conflicts with explicit governed surname scope"
            )
    else:
        typed_filters.append(
            {"target_type": "person", "property": "surname", "operator": "eq", "value": surname}
        )
        provenance.append({"field": "person.surname", "source": "governed_query_completion"})
    completed["typed_filters"] = typed_filters

    expected_operation = _explicit_governed_operation(query)
    actual_operation = completed.get("structured_operation")
    if expected_operation and actual_operation is None:
        completed["structured_operation"] = expected_operation
        provenance.append({"field": "structured_operation", "source": "governed_query_completion"})
    elif expected_operation and actual_operation != expected_operation:
        raise GovernedSemanticConflict(
            "provider operation conflicts with explicit governed query operation"
        )
    completed["semantic_provenance"] = provenance
    return completed


def _complete_explicit_person_inventory(
    payload: dict[str, object], query: str
) -> dict[str, object]:
    """Complete the unambiguous active-corpus Person-list request.

    ``kişileri listele`` is already an exhaustive inventory request in Turkish;
    requiring an additional quantifier such as ``tüm`` would make equivalent
    user wording depend on model interpretation.  The completion remains
    narrow: it accepts no filters, relations, grouping, or ordering and never
    repurposes a more specific query.
    """
    if not _EXPLICIT_LIST_PATTERN.search(query) or _explicit_surname_population(query):
        return dict(payload)
    completed = dict(payload)
    if any(
        completed.get(key)
        for key in (
            "typed_filters",
            "relations",
            "group_by",
            "relation_aggregate",
            "rank_direction",
        )
    ):
        return completed
    operation = completed.get("structured_operation")
    if operation not in {None, "list"}:
        return completed
    provenance = list(completed.get("semantic_provenance") or [])
    if not any(
        isinstance(item, dict) and item.get("field") == "structured_operation"
        for item in provenance
    ):
        provenance.append(
            {"field": "structured_operation", "source": "governed_query_completion"}
        )
    return {
        **completed,
        "state": "resolved",
        "entities": [],
        "targets": [
            {
                "target_type": "person",
                "description": "people mentioned in the active documents",
            }
        ],
        "structured_operation": "list",
        "operators": ["enumerate"],
        "coverage": "corpus_required",
        "candidates": [],
        "ambiguity_reasons": [],
        "unresolved_questions": [],
        "semantic_provenance": provenance,
    }


def _explicit_surname_population(query: str) -> str | None:
    for pattern in _SURNAME_POPULATION_PATTERNS:
        match = pattern.search(query)
        if match:
            return match.group("surname")
    return None


def _explicit_governed_operation(query: str) -> str | None:
    if _EXPLICIT_COUNT_PATTERN.search(query):
        return "count"
    # Ranking language retains its provider-owned aggregate and rank operation;
    # "listele" describes its presentation, not a contradictory list operation.
    if any(term in query.casefold() for term in _ANALYTIC_TERMS):
        return None
    if _EXPLICIT_LIST_PATTERN.search(query):
        return "list"
    return None


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
