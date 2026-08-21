"""Canonical entities, mentions, aliases, and identity boundary."""

from .identity import merge_entities, resolve_conservatively, split_entity
from .model import (
    CanonicalEntity,
    EntityAlias,
    EntityMention,
    EntityType,
    IdentityDecisionKind,
    IdentityOperation,
    IdentityResolution,
    ResolutionCandidate,
    normalize_mention,
)

__all__ = [
    "CanonicalEntity",
    "EntityAlias",
    "EntityMention",
    "EntityType",
    "IdentityDecisionKind",
    "IdentityOperation",
    "IdentityResolution",
    "ResolutionCandidate",
    "merge_entities",
    "normalize_mention",
    "resolve_conservatively",
    "split_entity",
]
