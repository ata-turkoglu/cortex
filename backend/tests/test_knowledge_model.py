from uuid import UUID

import pytest

from app.knowledge import KnowledgeAuthority, new_canonical_id
from app.knowledge.claims import (
    ClaimStage,
    KnowledgeClaim,
    ValidationOutcome,
    ValidatorDecision,
    link_contradiction,
    preferred_claim,
)
from app.knowledge.entities import (
    CanonicalEntity,
    EntityMention,
    EntityType,
    IdentityDecisionKind,
    ResolutionCandidate,
    merge_entities,
    resolve_conservatively,
    split_entity,
)
from app.knowledge.events import CanonicalEvent, EventParticipant
from app.knowledge.provenance import ExactSourceProvenance
from app.knowledge.relations import CanonicalRelation, RelationSupport
from app.knowledge.temporal import TemporalExpression, TemporalPrecision


def provenance(*, workspace_id="workspace-a", version="version-a", text="Ankara"):
    return ExactSourceProvenance(
        workspace_id=workspace_id,
        document_id="document-a",
        document_version_id=version,
        logical_document_id="logical-a",
        chunk_id="chunk-a",
        start_offset=10,
        end_offset=10 + len(text),
        source_text=text,
        extraction_run_id="run-a",
        provider="openai",
        model="model-a",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        confidence=0.9,
        validation_state="extracted",
        generation="generation-a",
    )


def mention(text="Ankara", *, version="version-a"):
    return EntityMention(new_canonical_id(), text, EntityType.LOCATION, provenance(version=version))


def test_canonical_ids_are_opaque_and_stable_after_display_name_changes():
    entity = CanonicalEntity.create(EntityType.PERSON, "Ayşe Yılmaz")
    UUID(entity.entity_id)
    renamed = CanonicalEntity(
        entity.entity_id,
        entity.entity_type,
        "Ayşe Kaya",
        KnowledgeAuthority.USER_CURATED,
    )
    assert renamed.entity_id == entity.entity_id
    with pytest.raises(ValueError, match="opaque UUID"):
        CanonicalEntity("ayse-yilmaz", EntityType.PERSON, "Ayşe", KnowledgeAuthority.EXTRACTED)


def test_exact_source_provenance_requires_a_complete_exact_span():
    first = provenance()
    assert UUID(first.evidence_id)
    assert first.evidence_id == provenance().evidence_id
    with pytest.raises(ValueError, match="exactly match"):
        ExactSourceProvenance(**{**first.__dict__, "end_offset": first.end_offset + 1})
    with pytest.raises(ValueError, match="complete source"):
        ExactSourceProvenance(**{**first.__dict__, "logical_document_id": ""})


def test_conservative_resolution_needs_unique_exact_corroboration():
    item = mention()
    weak = ResolutionCandidate(
        new_canonical_id(),
        EntityType.LOCATION,
        frozenset({"ankara"}),
        frozenset({"evidence-a"}),
        frozenset({"version-a"}),
    )
    assert resolve_conservatively(item, (weak,)).decision is IdentityDecisionKind.UNRESOLVED
    strong = ResolutionCandidate(
        new_canonical_id(),
        EntityType.LOCATION,
        frozenset({"ankara"}),
        frozenset({"evidence-a", "evidence-b"}),
        frozenset({"version-a", "version-b"}),
    )
    resolved = resolve_conservatively(item, (strong,))
    assert resolved.decision is IdentityDecisionKind.AUTO_LINK
    assert resolved.resolved_entity_id == strong.entity_id
    ambiguous = resolve_conservatively(item, (strong, strong))
    assert ambiguous.decision is IdentityDecisionKind.UNRESOLVED


def test_merge_and_split_are_lossless_and_user_curation_wins():
    first_mention = mention("A. Yılmaz", version="version-a")
    second_mention = mention("Ayşe Yılmaz", version="version-b")
    primary = CanonicalEntity.create(
        EntityType.PERSON,
        "A. Yılmaz",
        mentions=(first_mention,),
    )
    curated = CanonicalEntity.create(
        EntityType.PERSON,
        "Ayşe Yılmaz",
        KnowledgeAuthority.USER_CURATED,
        mentions=(second_mention,),
    )

    merged, superseded, merge = merge_entities(
        primary, (curated,), evidence_ids=(provenance().evidence_id,), reason="same person"
    )
    assert merged.entity_id == primary.entity_id
    assert merged.display_name == "Ayşe Yılmaz"
    assert merged.authority is KnowledgeAuthority.USER_CURATED
    assert {item.mention_id for item in merged.mentions} == {
        first_mention.mention_id,
        second_mention.mention_id,
    }
    assert superseded[0].status == "superseded"
    assert merge.source_entity_ids == (primary.entity_id, curated.entity_id)

    source, results, split = split_entity(
        merged,
        (("A. Yılmaz", (first_mention,)), ("Ayşe Yılmaz", (second_mention,))),
        evidence_ids=(provenance().evidence_id,),
        reason="mentions refer to different people",
    )
    assert source.status == "split"
    assert {mention.mention_id for result in results for mention in result.mentions} == {
        first_mention.mention_id,
        second_mention.mention_id,
    }
    assert split.source_entity_ids == (merged.entity_id,)


def test_claims_need_evidence_and_a_real_validator_and_keep_contradictions():
    subject_id = new_canonical_id()
    extracted = KnowledgeClaim(
        new_canonical_id(),
        subject_id,
        "registered_city",
        "Ankara",
        ClaimStage.EXTRACTED,
        KnowledgeAuthority.EXTRACTED,
        "generation-a",
    )
    with pytest.raises(ValueError, match="supported before"):
        extracted.verify(
            ValidatorDecision("llm-confidence", "1", ValidationOutcome.PASSED, "high score")
        )
    supported = extracted.support((provenance(),))
    with pytest.raises(ValueError, match="cannot verify"):
        supported.verify(
            ValidatorDecision("rule", "1", ValidationOutcome.FAILED, "format mismatch")
        )
    verified = supported.verify(
        ValidatorDecision("city-registry", "1", ValidationOutcome.PASSED, "registry match")
    )
    conflicting = KnowledgeClaim(
        new_canonical_id(),
        subject_id,
        "registered_city",
        "İzmir",
        ClaimStage.SUPPORTED,
        KnowledgeAuthority.VALIDATED,
        "generation-a",
        (provenance(text="İzmir"),),
    )
    conflict = link_contradiction(verified, conflicting)
    assert conflict.left_claim_id == verified.claim_id
    assert preferred_claim((verified, conflicting)) is None

    curated = KnowledgeClaim(
        new_canonical_id(),
        subject_id,
        "registered_city",
        "Ankara",
        ClaimStage.SUPPORTED,
        KnowledgeAuthority.USER_CURATED,
        "generation-a",
        (provenance(),),
    )
    assert preferred_claim((verified, conflicting, curated)) is curated


def test_relation_event_and_temporal_models_require_evidence_and_preserve_uncertainty():
    source_id, target_id = new_canonical_id(), new_canonical_id()
    relation = CanonicalRelation(
        new_canonical_id(),
        source_id,
        target_id,
        "owns",
        KnowledgeAuthority.VALIDATED,
        "generation-a",
        RelationSupport.EXACT_SPAN,
        (provenance(),),
        {"share": "1/2"},
    )
    temporal = TemporalExpression(
        new_canonical_id(),
        "yaklaşık 1990",
        "1990",
        None,
        "event_date",
        TemporalPrecision.APPROXIMATE,
        True,
        "generation-a",
        provenance(text="yaklaşık 1990"),
    )
    event = CanonicalEvent(
        new_canonical_id(),
        "ownership_transfer",
        "Mülkiyet devri",
        KnowledgeAuthority.VALIDATED,
        "generation-a",
        (EventParticipant(source_id, "buyer"), EventParticipant(target_id, "asset")),
        (provenance(),),
        (temporal.temporal_id,),
    )

    assert relation.support is RelationSupport.EXACT_SPAN
    assert temporal.uncertain is True
    assert event.temporal_expression_ids == (temporal.temporal_id,)
    with pytest.raises(ValueError, match="retain uncertainty"):
        TemporalExpression(
            new_canonical_id(),
            "1990 civarı",
            "1990",
            None,
            "event_date",
            TemporalPrecision.APPROXIMATE,
            False,
            "generation-a",
            provenance(text="1990 civarı"),
        )
