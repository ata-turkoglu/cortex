"""Exact-evidence promotion of extracted entity mentions into canonical Neo4j proposals."""

from dataclasses import dataclass
from typing import Protocol

from .entities import CanonicalEntity, EntityMention, EntityType
from .extraction import KnowledgeExtractionBundle, validate_extraction
from .model import KnowledgeAuthority, new_canonical_id
from .pipeline import CorpusSnapshot


class CanonicalEntityStore(Protocol):
    workspace_id: str

    def upsert_canonical_entity(self, entity: CanonicalEntity, generation: str) -> None: ...


@dataclass(frozen=True)
class PromotionSummary:
    entity_count: int
    mention_count: int


def promote_extracted_entities(
    store: CanonicalEntityStore,
    snapshot: CorpusSnapshot,
    generation_id: str,
    bundles: tuple[KnowledgeExtractionBundle, ...],
) -> PromotionSummary:
    """Persist extracted proposals without resolving or overwriting curated identities."""
    if store.workspace_id != snapshot.workspace_id:
        raise ValueError("canonical store and snapshot must have the same workspace")
    entity_count = 0
    mention_count = 0
    for bundle in bundles:
        evidence = validate_extraction(bundle, snapshot, generation_id)
        mention_evidence = evidence[: len(bundle.mentions)]
        for extracted, provenance in zip(bundle.mentions, mention_evidence, strict=True):
            try:
                entity_type = EntityType(extracted.entity_type)
            except ValueError as exc:
                raise ValueError(
                    f"unsupported extracted entity type: {extracted.entity_type}"
                ) from exc
            mention = EntityMention(
                new_canonical_id(), extracted.span.source_text, entity_type, provenance
            )
            entity = CanonicalEntity.create(
                entity_type,
                extracted.span.source_text,
                KnowledgeAuthority.EXTRACTED,
                mentions=(mention,),
            )
            # The Neo4j adapter enforces authority rank, so extracted proposals cannot
            # overwrite validated or user-curated entity fields.
            store.upsert_canonical_entity(entity, generation_id)
            entity_count += 1
            mention_count += 1
    return PromotionSummary(entity_count, mention_count)
