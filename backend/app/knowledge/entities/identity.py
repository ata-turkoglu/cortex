"""Conservative and reversible canonical identity decisions."""

from dataclasses import replace

from ..model import KnowledgeAuthority, new_canonical_id
from .model import (
    CanonicalEntity,
    EntityAlias,
    EntityMention,
    IdentityDecisionKind,
    IdentityOperation,
    IdentityResolution,
    ResolutionCandidate,
)


def resolve_conservatively(
    mention: EntityMention, candidates: tuple[ResolutionCandidate, ...]
) -> IdentityResolution:
    matching = tuple(
        candidate
        for candidate in candidates
        if candidate.entity_type == mention.entity_type
        and mention.normalized_text in candidate.normalized_aliases
        and len(candidate.supporting_evidence_ids) >= 2
        and len(candidate.supporting_document_version_ids) >= 2
    )
    if len(matching) != 1:
        return IdentityResolution(
            mention.mention_id,
            IdentityDecisionKind.UNRESOLVED,
            None,
            tuple(candidate.entity_id for candidate in candidates),
            "no unique candidate has exact-name support from two document versions",
        )
    candidate = matching[0]
    return IdentityResolution(
        mention.mention_id,
        IdentityDecisionKind.AUTO_LINK,
        candidate.entity_id,
        tuple(item.entity_id for item in candidates),
        "unique exact-name candidate corroborated by two document versions",
    )


def merge_entities(
    primary: CanonicalEntity,
    others: tuple[CanonicalEntity, ...],
    *,
    evidence_ids: tuple[str, ...],
    reason: str,
) -> tuple[CanonicalEntity, tuple[CanonicalEntity, ...], IdentityOperation]:
    if not others:
        raise ValueError("merge requires at least two entities")
    if any(entity.entity_type != primary.entity_type for entity in others):
        raise ValueError("entities of different upper types cannot be merged")
    all_entities = (primary, *others)
    authority = max(entity.authority for entity in all_entities)
    authoritative = next(entity for entity in all_entities if entity.authority == authority)
    aliases = {alias.normalized_value: alias for entity in all_entities for alias in entity.aliases}
    for entity in all_entities:
        aliases.setdefault(
            entity.display_name.casefold(),
            EntityAlias(new_canonical_id(), entity.display_name, entity.authority),
        )
    merged = replace(
        primary,
        display_name=authoritative.display_name,
        authority=authority,
        aliases=tuple(aliases.values()),
        mentions=tuple(mention for entity in all_entities for mention in entity.mentions),
    )
    superseded = tuple(replace(entity, status="superseded") for entity in others)
    operation = IdentityOperation(
        new_canonical_id(),
        IdentityDecisionKind.MERGE,
        KnowledgeAuthority.USER_CURATED,
        tuple(entity.entity_id for entity in all_entities),
        (merged.entity_id,),
        evidence_ids,
        reason,
    )
    return merged, superseded, operation


def split_entity(
    source: CanonicalEntity,
    partitions: tuple[tuple[str, tuple[EntityMention, ...]], ...],
    *,
    evidence_ids: tuple[str, ...],
    reason: str,
) -> tuple[CanonicalEntity, tuple[CanonicalEntity, ...], IdentityOperation]:
    if len(partitions) < 2:
        raise ValueError("split requires at least two result entities")
    mention_ids = [mention.mention_id for _, mentions in partitions for mention in mentions]
    if len(mention_ids) != len(set(mention_ids)):
        raise ValueError("a mention cannot be assigned to more than one split result")
    if set(mention_ids) != {mention.mention_id for mention in source.mentions}:
        raise ValueError("split must assign every original mention exactly once")
    results = tuple(
        CanonicalEntity.create(
            source.entity_type,
            display_name,
            KnowledgeAuthority.USER_CURATED,
            subtype=source.subtype,
            mentions=mentions,
        )
        for display_name, mentions in partitions
    )
    operation = IdentityOperation(
        new_canonical_id(),
        IdentityDecisionKind.SPLIT,
        KnowledgeAuthority.USER_CURATED,
        (source.entity_id,),
        tuple(entity.entity_id for entity in results),
        evidence_ids,
        reason,
    )
    return replace(source, status="split"), results, operation
