"""Build typed exact-evidence knowledge proposals before graph persistence."""

from dataclasses import dataclass
from typing import Protocol

from .claims import ClaimStage, KnowledgeClaim
from .events import CanonicalEvent, EventParticipant
from .extraction import KnowledgeExtractionBundle, validate_extraction
from .model import KnowledgeAuthority, new_canonical_id
from .pipeline import CorpusSnapshot
from .relations import CanonicalRelation, RelationSupport
from .temporal import TemporalExpression, TemporalPrecision


@dataclass(frozen=True)
class ConstructedKnowledge:
    relations: tuple[CanonicalRelation, ...]
    events: tuple[CanonicalEvent, ...]
    temporals: tuple[TemporalExpression, ...]
    claims: tuple[KnowledgeClaim, ...]


class CanonicalClaimStore(Protocol):
    workspace_id: str

    def upsert_claim(self, claim: KnowledgeClaim) -> None: ...


class CanonicalKnowledgeStore(CanonicalClaimStore, Protocol):
    def upsert_relation(self, relation: CanonicalRelation) -> None: ...

    def upsert_event(self, event: CanonicalEvent) -> None: ...

    def upsert_temporal(self, temporal: TemporalExpression) -> None: ...


def promote_constructed_claims(
    store: CanonicalClaimStore, snapshot: CorpusSnapshot, constructed: ConstructedKnowledge
) -> int:
    """Persist evidence-gated claims through the sole canonical graph boundary."""
    if store.workspace_id != snapshot.workspace_id:
        raise ValueError("canonical store and snapshot must have the same workspace")
    for claim in constructed.claims:
        store.upsert_claim(claim)
    return len(constructed.claims)


def promote_constructed_knowledge(
    store: CanonicalKnowledgeStore, snapshot: CorpusSnapshot, constructed: ConstructedKnowledge
) -> dict[str, int]:
    """Write typed canonical proposals only through the workspace-scoped graph boundary."""
    if store.workspace_id != snapshot.workspace_id:
        raise ValueError("canonical store and snapshot must have the same workspace")
    for relation in constructed.relations:
        store.upsert_relation(relation)
    for event in constructed.events:
        store.upsert_event(event)
    for temporal in constructed.temporals:
        store.upsert_temporal(temporal)
    claim_count = promote_constructed_claims(store, snapshot, constructed)
    return {
        "relations": len(constructed.relations),
        "events": len(constructed.events),
        "temporals": len(constructed.temporals),
        "claims": claim_count,
    }


def construct_from_bundle(
    bundle: KnowledgeExtractionBundle,
    snapshot: CorpusSnapshot,
    generation_id: str,
    mention_entity_ids: dict[str, str],
) -> ConstructedKnowledge:
    """Convert one validated bundle without inferring unresolved identity links."""
    evidence = validate_extraction(bundle, snapshot, generation_id)
    offset = len(bundle.mentions)
    relation_evidence = evidence[offset : offset + len(bundle.relations)]
    offset += len(bundle.relations)
    event_evidence = evidence[offset : offset + len(bundle.events)]
    offset += len(bundle.events)
    temporal_evidence = evidence[offset : offset + len(bundle.temporals)]
    offset += len(bundle.temporals)
    claim_evidence = evidence[offset : offset + len(bundle.claims)]
    relation_items = []
    for item, source in zip(bundle.relations, relation_evidence, strict=True):
        if (
            item.source_mention_id not in mention_entity_ids
            or item.target_mention_id not in mention_entity_ids
        ):
            raise ValueError("relation needs resolved canonical entity IDs")
        relation_items.append(
            CanonicalRelation(
                new_canonical_id(),
                mention_entity_ids[item.source_mention_id],
                mention_entity_ids[item.target_mention_id],
                item.relation_type,
                KnowledgeAuthority.EXTRACTED,
                generation_id,
                RelationSupport.EXACT_SPAN,
                (source,),
                {},
            )
        )
    temporal_items = tuple(
        TemporalExpression(
            new_canonical_id(),
            item.original_text,
            item.normalized_start,
            item.normalized_end,
            item.semantic_role,
            TemporalPrecision(item.precision),
            item.uncertain,
            generation_id,
            source,
        )
        for item, source in zip(bundle.temporals, temporal_evidence, strict=True)
    )
    event_items = []
    for item, source in zip(bundle.events, event_evidence, strict=True):
        missing = set(item.participant_mention_ids) - mention_entity_ids.keys()
        if missing:
            raise ValueError("event needs resolved canonical participant IDs")
        event_items.append(
            CanonicalEvent(
                new_canonical_id(),
                item.event_type,
                item.event_type,
                KnowledgeAuthority.EXTRACTED,
                generation_id,
                tuple(
                    EventParticipant(mention_entity_ids[value], "participant")
                    for value in item.participant_mention_ids
                ),
                (source,),
            )
        )
    claim_items = []
    for item, source in zip(bundle.claims, claim_evidence, strict=True):
        subject_id = mention_entity_ids.get(item.subject_mention_id)
        if not subject_id:
            raise ValueError("claim needs a resolved canonical subject ID")
        claim_items.append(
            KnowledgeClaim(
                new_canonical_id(),
                subject_id,
                item.predicate,
                item.value,
                ClaimStage.SUPPORTED,
                KnowledgeAuthority.EXTRACTED,
                generation_id,
                (source,),
            )
        )
    return ConstructedKnowledge(
        tuple(relation_items), tuple(event_items), temporal_items, tuple(claim_items)
    )
