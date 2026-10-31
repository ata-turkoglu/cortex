import asyncio
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.providers.base import GeneratedText
from app.query.context import (
    ContextEntityReference,
    ConversationContext,
    ConversationContextState,
    ConversationTurn,
)
from app.query.ir import lower_semantic_understanding
from app.query.understanding import (
    InterpretationCandidate,
    PlannerModel,
    SemanticEntity,
    SemanticPlannerAdapter,
    SemanticTarget,
    SemanticTemporalConstraint,
    SemanticTypedFilter,
    SemanticUnderstanding,
    complete_governed_semantics,
    select_planner_tier,
)


def _context(*, candidate: bool = False, history_count: int = 0) -> ConversationContext:
    candidate_references = (
        (
            ContextEntityReference(
                mention="he",
                resolution="ambiguous",
                candidate_entity_ids=("person-1", "person-2"),
            ),
        )
        if candidate
        else ()
    )
    return ConversationContext(
        workspace_id="workspace-1",
        conversation_id="conversation-1",
        revision=1,
        history=tuple(
            ConversationTurn(
                message_id=f"message-{index}",
                role="user",
                content="history",
                created_at=datetime.now(UTC),
            )
            for index in range(history_count)
        ),
        state=ConversationContextState(candidate_references=candidate_references),
    )


def _resolved(confidence: float = 0.9) -> SemanticUnderstanding:
    return SemanticUnderstanding(
        state="resolved",
        entities=(
            SemanticEntity(
                reference_id="person",
                mention="Hasan Tahsin Merter",
                entity_type="person",
                resolution="resolved",
                canonical_entity_id="person-1",
                display_name="Hasan Tahsin Merter",
            ),
        ),
        targets=(
            SemanticTarget(
                target_type="entity", reference_id="person", description="the named person"
            ),
        ),
        operators=("describe", "retrieve_evidence"),
        coverage="relevant_evidence",
        confidence=confidence,
    )


class FakeStructuredProvider:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    async def generate_structured(self, model, instructions, input_text, **schema):
        self.calls.append(
            {"model": model, "instructions": instructions, "input": input_text, **schema}
        )
        return GeneratedText(text=self.outputs.pop(0))


def test_semantic_schema_has_no_v2_intent_and_forbids_extra_fields():
    schema_text = json.dumps(SemanticUnderstanding.model_json_schema()).casefold()
    assert '"intent"' not in schema_text
    payload = _resolved().model_dump(mode="json") | {"intent": "describe"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SemanticUnderstanding.model_validate(payload)


def test_temporal_roles_preserve_range_relative_approximate_and_partial_meaning():
    temporals = (
        SemanticTemporalConstraint(
            role="range",
            original_text="1988-1992",
            normalized_start="1988",
            normalized_end="1992",
            precision="year",
            uncertainty="certain",
        ),
        SemanticTemporalConstraint(
            role="before_event",
            original_text="before the sale",
            precision="unknown",
            anchor_event="sale",
        ),
        SemanticTemporalConstraint(
            role="approximate_date",
            original_text="around 1990",
            normalized_start="1990",
            precision="year",
            uncertainty="approximate",
        ),
        SemanticTemporalConstraint(
            role="partial_date",
            original_text="March 1988",
            normalized_start="1988-03",
            precision="month",
            uncertainty="certain",
        ),
    )
    assert [item.role for item in temporals] == [
        "range",
        "before_event",
        "approximate_date",
        "partial_date",
    ]
    with pytest.raises(ValidationError, match="anchor_event"):
        SemanticTemporalConstraint(
            role="after_event", original_text="afterward", precision="unknown"
        )


def test_planner_repairs_invalid_output_then_escalates_low_confidence():
    low = _resolved(confidence=0.2)
    high = _resolved(confidence=0.95)
    provider = FakeStructuredProvider(["not-json", low.model_dump_json(), high.model_dump_json()])
    models = {
        "simple": PlannerModel("fake", "simple-model"),
        "standard": PlannerModel("fake", "standard-model"),
        "complex": PlannerModel("fake", "complex-model"),
    }
    planner = SemanticPlannerAdapter(
        models=models,
        providers={"fake": provider},
        repair_attempts=1,
        escalation_enabled=True,
        confidence_threshold=0.75,
    )
    result = asyncio.run(planner.plan("Who is Hasan?", _context()))

    assert result.selected_tier == "standard"
    assert result.escalated is True
    assert [call["model"] for call in provider.calls] == [
        "simple-model",
        "simple-model",
        "standard-model",
    ]
    schema = provider.calls[0]["json_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_planner_accepts_an_unfiltered_person_population_from_the_provider():
    understanding = SemanticUnderstanding(
        state="resolved",
        targets=(SemanticTarget(target_type="person", description="all active people"),),
        structured_operation="list",
        operators=("enumerate",),
        coverage="corpus_required",
        confidence=1.0,
    )
    provider = FakeStructuredProvider([understanding.model_dump_json()])
    planner = SemanticPlannerAdapter(
        models={tier: PlannerModel("fake", "model") for tier in ("simple", "standard", "complex")},
        providers={"fake": provider},
    )

    result = asyncio.run(planner.plan("Arşivde kayıtlı bütün şahısları sıralar mısın?", _context()))

    assert len(result.attempts) == 1
    assert len(provider.calls) == 1
    assert result.understanding.structured_operation == "list"
    assert result.understanding.coverage == "corpus_required"
    assert result.understanding.targets[0].target_type == "person"


def test_planner_completes_explicit_person_list_without_requiring_tum():
    provider = FakeStructuredProvider([_resolved().model_dump_json()])
    planner = SemanticPlannerAdapter(
        models={tier: PlannerModel("fake", "model") for tier in ("simple", "standard", "complex")},
        providers={"fake": provider},
        escalation_enabled=False,
    )

    result = asyncio.run(
        planner.plan("Etkin belgelerde geçen kişileri listele", _context())
    )

    assert result.understanding.state == "resolved"
    assert result.understanding.structured_operation == "list"
    assert result.understanding.coverage == "corpus_required"
    assert [item.target_type for item in result.understanding.targets] == ["person"]
    assert result.understanding.entities == ()
    assert "enumerate" in result.understanding.operators


def test_planner_does_not_call_provider_for_active_document_person_inventory():
    provider = FakeStructuredProvider([])
    planner = SemanticPlannerAdapter(
        models={tier: PlannerModel("fake", "model") for tier in ("simple", "standard", "complex")},
        providers={"fake": provider},
    )

    result = asyncio.run(
        planner.plan("Etkin belgelerde geçen tüm kişileri listele", _context())
    )

    assert provider.calls == []
    assert result.understanding.structured_operation == "list"
    assert result.attempts[0].provider == "deterministic"


def test_planner_normalizes_live_shaped_governed_count_to_typed_operation():
    live_shape = SemanticUnderstanding(
        state="resolved",
        targets=(SemanticTarget(target_type="entity", description="Merter people"),),
        typed_filters=(
            SemanticTypedFilter(
                target_type="person", property="surname", operator="eq", value="Merter"
            ),
        ),
        operators=("filter", "aggregate"),
        coverage="corpus_required",
        confidence=1.0,
    )
    provider = FakeStructuredProvider([live_shape.model_dump_json()])
    planner = SemanticPlannerAdapter(
        models={tier: PlannerModel("fake", "model") for tier in ("simple", "standard", "complex")},
        providers={"fake": provider},
        escalation_enabled=False,
    )

    result = asyncio.run(planner.plan("Merter soyadlı kaç kişi var?", _context()))

    assert result.understanding.structured_operation == "count"


def test_governed_completion_adds_only_missing_explicit_count_population_facts():
    completed = complete_governed_semantics(
        {"state": "resolved", "confidence": 1.0}, "Merter soyadli kac kisi var?"
    )

    assert completed["structured_operation"] == "count"
    assert completed["typed_filters"] == [
        {"target_type": "person", "property": "surname", "operator": "eq", "value": "Merter"}
    ]
    assert completed["semantic_provenance"] == [
        {"field": "person.surname", "source": "governed_query_completion"},
        {"field": "structured_operation", "source": "governed_query_completion"},
    ]


def test_unresolved_descriptive_retrieval_is_a_valid_schema_and_lowers_to_evidence():
    provider_shape = {
        "schema_version": "1.0",
        "state": "unresolved",
        "entities": [
            {
                "reference_id": "person",
                "mention": "Hasan Tahsin Merter",
                "entity_type": "person",
                "reference_kind": "explicit",
                "resolution": "unresolved",
                "canonical_entity_id": None,
                "canonical_entity_ids": [],
                "display_name": None,
                "candidate_entity_ids": [],
            }
        ],
        "targets": [
            {
                "target_type": "entity",
                "reference_id": "person",
                "description": "available evidence",
            }
        ],
        "relations": [],
        "temporal_constraints": [],
        "typed_filters": [],
        "structured_operation": None,
        "group_by": None,
        "rank_direction": None,
        "relation_aggregate": None,
        "operators": ["describe", "retrieve_evidence"],
        "uses_temporal_focus": False,
        "coverage": "relevant_evidence",
        "candidates": [],
        "ambiguity_reasons": [],
        "unresolved_questions": [],
        "semantic_provenance": [],
        "confidence": 0.95,
    }

    understanding = SemanticUnderstanding.model_validate(provider_shape)
    ir = lower_semantic_understanding(understanding, "workspace-1")

    assert understanding.unresolved_questions == ()
    assert [node.kind for node in ir.nodes] == ["retrieve_evidence", "summarize"]


def test_production_strict_schema_uses_typed_provenance_records():
    provider = FakeStructuredProvider([_resolved().model_dump_json()])
    planner = SemanticPlannerAdapter(
        models={tier: PlannerModel("fake", "model") for tier in ("simple", "standard", "complex")},
        providers={"fake": provider},
        escalation_enabled=False,
    )

    asyncio.run(planner.plan("Who is Hasan?", _context()))

    schema = provider.calls[0]["json_schema"]
    provenance = schema["$defs"]["SemanticProvenance"]
    assert provenance["additionalProperties"] is False
    assert provenance["required"] == ["field", "source"]
    assert provenance["properties"]["field"]["enum"] == [
        "person.surname",
        "structured_operation",
    ]
    assert provenance["properties"]["source"]["enum"] == [
        "provider",
        "governed_query_completion",
    ]


def test_turkish_dotted_exact_event_date_normalizes_and_impossible_day_fails_validation():
    temporal = SemanticTemporalConstraint(
        role="event_date",
        original_text="12.06.1974",
        precision="day",
        uncertainty="certain",
    )

    assert temporal.normalized_start == temporal.normalized_end == "1974-06-12"
    with pytest.raises(ValidationError, match="valid ISO day"):
        SemanticTemporalConstraint(
            role="event_date",
            original_text="31.02.1974",
            normalized_start="1974-02-31",
            normalized_end="1974-02-31",
            precision="day",
            uncertainty="certain",
        )


def test_ambiguity_and_unresolved_states_are_explicit_and_drive_tier_selection():
    entity = SemanticEntity(reference_id="person", mention="he", reference_kind="follow_up")
    candidates = tuple(
        InterpretationCandidate(
            label=f"candidate {index}",
            explanation="different referent",
            entities=(entity,),
            confidence=0.5,
        )
        for index in (1, 2)
    )
    ambiguous = SemanticUnderstanding(
        state="ambiguous",
        entities=(entity,),
        candidates=candidates,
        ambiguity_reasons=("multiple possible people",),
        confidence=0.5,
    )
    unresolved = SemanticUnderstanding(
        state="unresolved",
        entities=(entity,),
        unresolved_questions=("Which person do you mean?",),
        confidence=0.1,
    )
    assert ambiguous.state == "ambiguous"
    assert unresolved.state == "unresolved"
    assert select_planner_tier("short", _context(candidate=True)) == "complex"
    assert select_planner_tier("short", _context(history_count=7)) == "standard"
    assert (
        select_planner_tier(
            "Merter soyadlı kişileri listele ve taşınmaz sayılarına göre "
            "en fazladan en aza sırala.",
            _context(),
    )
    == "standard"
    )


def test_failed_planner_attempts_keep_their_billed_responses():
    from app.query.understanding.planner import SemanticPlannerOutputError

    provider = FakeStructuredProvider(["not-json", "still-not-json"])
    models = {
        tier: PlannerModel("fake", f"{tier}-model") for tier in ("simple", "standard", "complex")
    }
    planner = SemanticPlannerAdapter(
        models=models, providers={"fake": provider}, repair_attempts=1, escalation_enabled=False
    )

    with pytest.raises(SemanticPlannerOutputError) as raised:
        asyncio.run(planner.plan("Who is Hasan?", _context()))

    assert [attempt.generated.text for attempt in raised.value.attempts] == [
        "not-json",
        "still-not-json",
    ]
