from app.query.context import (
    ContextCanonicalResultSet,
    ContextEntityReference,
    ContextTemporalFocus,
    ConversationContext,
    ConversationContextState,
)
from app.query.understanding import (
    SemanticEntity,
    SemanticRelation,
    SemanticUnderstanding,
    apply_conversation_context,
    evolve_context_state,
)


def _follow_up(*, temporal: bool = False) -> SemanticUnderstanding:
    return SemanticUnderstanding(
        state="unresolved",
        entities=(
            SemanticEntity(
                reference_id="parent",
                mention="the children",
                entity_type="person",
                reference_kind="follow_up",
            ),
        ),
        relations=(SemanticRelation(predicate="children_of", subject_reference_id="parent"),),
        operators=("resolve_reference", "traverse_relation"),
        uses_temporal_focus=temporal,
        unresolved_questions=("Whose children?",),
        confidence=0.8,
    )


def _context(state: ConversationContextState) -> ConversationContext:
    return ConversationContext(
        workspace_id="workspace-1",
        conversation_id="conversation-1",
        revision=1,
        state=state,
    )


def test_follow_up_carries_the_last_compatible_resolved_entity():
    context = _context(
        ConversationContextState(
            resolved_entities=(
                ContextEntityReference(
                    mention="Hasan Tahsin Merter",
                    entity_type="person",
                    resolution="resolved",
                    canonical_entity_id="person-1",
                    display_name="Hasan Tahsin Merter",
                ),
            )
        )
    )

    result = apply_conversation_context(_follow_up(), context)

    assert result.state == "resolved"
    assert result.entities[0].canonical_entity_id == "person-1"
    assert result.relations[0].predicate == "children_of"
    assert result.unresolved_questions == ()


def test_follow_up_preserves_ambiguous_context_candidates():
    context = _context(
        ConversationContextState(
            candidate_references=(
                ContextEntityReference(
                    mention="he",
                    entity_type="person",
                    resolution="ambiguous",
                    candidate_entity_ids=("person-1", "person-2"),
                ),
            )
        )
    )

    result = apply_conversation_context(_follow_up(), context)

    assert result.state == "ambiguous"
    assert result.entities[0].candidate_entity_ids == ("person-1", "person-2")
    assert [item.entities[0].canonical_entity_id for item in result.candidates] == [
        "person-1",
        "person-2",
    ]


def test_temporal_focus_carries_role_precision_uncertainty_and_original_text():
    context = _context(
        ConversationContextState(
            resolved_entities=(
                ContextEntityReference(
                    mention="Hasan",
                    entity_type="person",
                    resolution="resolved",
                    canonical_entity_id="person-1",
                ),
            ),
            temporal_focus=(
                ContextTemporalFocus(
                    original_text="around March 1988",
                    semantic_role="approximate_date",
                    normalized_start="1988-03",
                    precision="month",
                    uncertainty="approximate",
                ),
            ),
        )
    )

    result = apply_conversation_context(_follow_up(temporal=True), context)

    assert result.state == "resolved"
    assert result.temporal_constraints[0].model_dump() == {
        "role": "approximate_date",
        "original_text": "around March 1988",
        "normalized_start": "1988-03",
        "normalized_end": None,
        "precision": "month",
        "uncertainty": "approximate",
        "anchor_event": None,
    }


def test_missing_requested_temporal_focus_stays_unresolved():
    context = _context(
        ConversationContextState(
            resolved_entities=(
                ContextEntityReference(
                    mention="Hasan",
                    entity_type="person",
                    resolution="resolved",
                    canonical_entity_id="person-1",
                ),
            )
        )
    )

    result = apply_conversation_context(_follow_up(temporal=True), context)

    assert result.state == "unresolved"
    assert "time period" in result.unresolved_questions[0]


def test_resolved_understanding_evolves_only_local_context_state():
    context = _context(
        ConversationContextState(
            candidate_references=(
                ContextEntityReference(
                    mention="he",
                    entity_type="person",
                    resolution="ambiguous",
                    candidate_entity_ids=("person-1", "person-2"),
                ),
            )
        )
    )
    understanding = SemanticUnderstanding(
        state="resolved",
        entities=(
            SemanticEntity(
                reference_id="person",
                mention="Hasan",
                entity_type="person",
                resolution="resolved",
                canonical_entity_id="person-1",
            ),
        ),
        confidence=0.9,
    )

    state = evolve_context_state(context, understanding, source_message_id="message-1")

    assert state.resolved_entities[-1].canonical_entity_id == "person-1"
    assert state.resolved_entities[-1].source_message_id == "message-1"
    assert state.candidate_references == ()


def test_conversation_result_referent_carries_final_canonical_id_set_only_in_generation():
    context = _context(
        ConversationContextState(
            last_final_entity_result=ContextCanonicalResultSet(
                canonical_entity_ids=("child-1", "child-2"),
                entity_type="person",
                generation_id="generation-1",
                source_message_id="message-1",
            )
        )
    )
    follow_up = SemanticUnderstanding(
        state="unresolved",
        entities=(
            SemanticEntity(
                reference_id="previous-results",
                mention="onlar",
                entity_type="person",
                reference_kind="conversation_result",
            ),
        ),
        relations=(
            SemanticRelation(predicate="parent_of", subject_reference_id="previous-results"),
        ),
        operators=("resolve_reference", "traverse_relation"),
        unresolved_questions=("Which previous results?",),
        confidence=0.9,
    )

    result = apply_conversation_context(follow_up, context, generation_id="generation-1")
    wrong_generation = apply_conversation_context(follow_up, context, generation_id="generation-2")

    assert result.state == "resolved"
    assert result.entities[0].canonical_entity_ids == ("child-1", "child-2")
    assert wrong_generation.state == "unresolved"
