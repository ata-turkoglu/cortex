"""Deterministic application of conversation-local entity and temporal focus."""

from __future__ import annotations

from ..context import (
    ContextEntityReference,
    ContextTemporalFocus,
    ConversationContext,
    ConversationContextState,
)
from .schemas import (
    InterpretationCandidate,
    SemanticEntity,
    SemanticTemporalConstraint,
    SemanticUnderstanding,
)


def apply_conversation_context(
    understanding: SemanticUnderstanding, context: ConversationContext
) -> SemanticUnderstanding:
    """Resolve marked follow-ups without turning conversation assumptions into KG facts."""
    if understanding.state == "ambiguous" and understanding.candidates:
        return understanding

    entities = list(understanding.entities)
    ambiguous_candidates: tuple[str, ...] = ()
    resolved_follow_ups = 0
    unresolved_follow_ups = 0
    for index, entity in enumerate(entities):
        if entity.reference_kind != "follow_up" or entity.resolution == "resolved":
            continue
        context_candidates = _candidate_ids(context, entity.entity_type)
        if len(context_candidates) > 1:
            ambiguous_candidates = context_candidates
            entities[index] = SemanticEntity.model_validate(
                {
                    **entity.model_dump(mode="json"),
                    "resolution": "ambiguous",
                    "canonical_entity_id": None,
                    "candidate_entity_ids": list(context_candidates),
                }
            )
            continue
        focus = _last_resolved_entity(context, entity.entity_type)
        if focus:
            entities[index] = SemanticEntity.model_validate(
                {
                    **entity.model_dump(mode="json"),
                    "resolution": "resolved",
                    "canonical_entity_id": focus.canonical_entity_id,
                    "display_name": focus.display_name or focus.mention,
                    "candidate_entity_ids": [],
                }
            )
            resolved_follow_ups += 1
        else:
            unresolved_follow_ups += 1

    temporals = list(understanding.temporal_constraints)
    missing_temporal_focus = False
    if understanding.uses_temporal_focus and not temporals:
        if context.state.temporal_focus:
            focus = context.state.temporal_focus[-1]
            temporals.append(
                SemanticTemporalConstraint(
                    role=focus.semantic_role,
                    original_text=focus.original_text,
                    normalized_start=focus.normalized_start,
                    normalized_end=focus.normalized_end,
                    precision=focus.precision,
                    uncertainty=focus.uncertainty,
                    anchor_event=focus.anchor_event,
                )
            )
        else:
            missing_temporal_focus = True

    payload = understanding.model_dump(mode="json")
    payload["entities"] = [item.model_dump(mode="json") for item in entities]
    payload["temporal_constraints"] = [item.model_dump(mode="json") for item in temporals]
    if ambiguous_candidates:
        payload.update(
            state="ambiguous",
            candidates=[
                _candidate(understanding, entities, candidate_id, index)
                for index, candidate_id in enumerate(ambiguous_candidates[:5], start=1)
            ],
            ambiguity_reasons=["the conversation contains multiple possible follow-up referents"],
            unresolved_questions=[],
        )
    elif missing_temporal_focus or unresolved_follow_ups:
        payload.update(
            state="unresolved",
            candidates=[],
            ambiguity_reasons=[],
            unresolved_questions=[
                (
                    "Which earlier time period should be carried forward?"
                    if missing_temporal_focus
                    else "Which earlier entity does this follow-up refer to?"
                )
            ],
        )
    elif resolved_follow_ups and _all_entities_resolved(entities):
        payload.update(
            state="resolved", candidates=[], ambiguity_reasons=[], unresolved_questions=[]
        )
    return SemanticUnderstanding.model_validate(payload)


def evolve_context_state(
    context: ConversationContext,
    understanding: SemanticUnderstanding,
    *,
    source_message_id: str,
) -> ConversationContextState:
    """Build the next local state; persistence remains an explicit short transaction."""
    resolved = list(context.state.resolved_entities)
    for entity in understanding.entities:
        if entity.resolution != "resolved" or not entity.canonical_entity_id:
            continue
        resolved = [
            item for item in resolved if item.canonical_entity_id != entity.canonical_entity_id
        ]
        resolved.append(
            ContextEntityReference(
                mention=entity.mention,
                entity_type=entity.entity_type,
                resolution="resolved",
                canonical_entity_id=entity.canonical_entity_id,
                display_name=entity.display_name,
                source_message_id=source_message_id,
            )
        )
    temporal_focus = list(context.state.temporal_focus)
    for temporal in understanding.temporal_constraints:
        temporal_focus.append(
            ContextTemporalFocus(
                original_text=temporal.original_text,
                semantic_role=temporal.role,
                normalized_start=temporal.normalized_start,
                normalized_end=temporal.normalized_end,
                precision=temporal.precision,
                uncertainty=temporal.uncertainty,
                anchor_event=temporal.anchor_event,
                source_message_id=source_message_id,
            )
        )
    return ConversationContextState(
        resolved_entities=tuple(resolved[-20:]),
        candidate_references=(
            ()
            if understanding.state == "resolved" and resolved
            else context.state.candidate_references
        ),
        temporal_focus=tuple(temporal_focus[-10:]),
        explicit_constraints=context.state.explicit_constraints,
        assumptions=context.state.assumptions,
    )


def _last_resolved_entity(
    context: ConversationContext, entity_type: str
) -> ContextEntityReference | None:
    matching = [
        item
        for item in context.state.resolved_entities
        if entity_type == "unknown" or item.entity_type == entity_type
    ]
    return matching[-1] if matching else None


def _candidate_ids(context: ConversationContext, entity_type: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            candidate_id
            for item in context.state.candidate_references
            if entity_type == "unknown" or item.entity_type == entity_type
            for candidate_id in item.candidate_entity_ids
        )
    )


def _candidate(
    understanding: SemanticUnderstanding,
    entities: list[SemanticEntity],
    canonical_entity_id: str,
    ordinal: int,
) -> dict[str, object]:
    candidate_entities = [
        SemanticEntity.model_validate(
            {
                **item.model_dump(mode="json"),
                "resolution": "resolved",
                "canonical_entity_id": canonical_entity_id,
                "candidate_entity_ids": [],
            }
        )
        if item.reference_kind == "follow_up" and item.resolution == "ambiguous"
        else item
        for item in entities
    ]
    return InterpretationCandidate(
        label=f"follow-up referent {ordinal}",
        explanation=f"carry the follow-up to canonical entity {canonical_entity_id}",
        entities=tuple(candidate_entities),
        targets=understanding.targets,
        relations=understanding.relations,
        temporal_constraints=understanding.temporal_constraints,
        operators=understanding.operators,
        confidence=understanding.confidence,
    ).model_dump(mode="json")


def _all_entities_resolved(entities: list[SemanticEntity]) -> bool:
    return all(item.resolution == "resolved" for item in entities)
