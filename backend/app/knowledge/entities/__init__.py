"""Canonical entities, mentions, aliases, and identity boundary."""

from .identity import merge_entities, resolve_conservatively, split_entity
from .model import (
    ENTITY_PROPERTY_VOCABULARY,
    CanonicalEntity,
    CanonicalEntityProperty,
    EntityAlias,
    EntityMention,
    EntityPropertyDefinition,
    EntityPropertyValueType,
    EntityType,
    IdentityDecisionKind,
    IdentityOperation,
    IdentityResolution,
    ResolutionCandidate,
    canonical_person_display_name,
    normalize_mention,
    normalize_person_identity,
)

__all__ = [
    "CanonicalEntity",
    "CanonicalEntityProperty",
    "ENTITY_PROPERTY_VOCABULARY",
    "EntityAlias",
    "EntityMention",
    "EntityPropertyDefinition",
    "EntityPropertyValueType",
    "EntityType",
    "IdentityDecisionKind",
    "IdentityOperation",
    "IdentityResolution",
    "canonical_person_display_name",
    "normalize_person_identity",
    "ResolutionCandidate",
    "merge_entities",
    "normalize_mention",
    "resolve_conservatively",
    "split_entity",
]
