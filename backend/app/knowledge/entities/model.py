"""Canonical entities, mentions, aliases, and reversible identity decisions."""

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from ..model import KnowledgeAuthority, new_canonical_id, require_canonical_id
from ..provenance import ExactSourceProvenance


def normalize_mention(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    ASSET_PROPERTY = "asset_property"
    DYNAMIC = "dynamic"


class IdentityDecisionKind(StrEnum):
    UNRESOLVED = "unresolved"
    AUTO_LINK = "auto_link"
    MANUAL_LINK = "manual_link"
    MERGE = "merge"
    SPLIT = "split"
    ALIAS_ADD = "alias_add"
    ALIAS_REMOVE = "alias_remove"


@dataclass(frozen=True)
class EntityAlias:
    alias_id: str
    value: str
    authority: KnowledgeAuthority
    active: bool = True

    def __post_init__(self) -> None:
        require_canonical_id(self.alias_id)
        if not normalize_mention(self.value):
            raise ValueError("alias value is required")

    @property
    def normalized_value(self) -> str:
        return normalize_mention(self.value)


@dataclass(frozen=True)
class EntityMention:
    mention_id: str
    original_text: str
    entity_type: EntityType
    provenance: ExactSourceProvenance
    candidate_entity_ids: tuple[str, ...] = ()
    resolved_entity_id: str | None = None
    decision: IdentityDecisionKind = IdentityDecisionKind.UNRESOLVED

    def __post_init__(self) -> None:
        require_canonical_id(self.mention_id)
        if not normalize_mention(self.original_text):
            raise ValueError("original mention text is required")
        for candidate_id in self.candidate_entity_ids:
            require_canonical_id(candidate_id)
        if self.resolved_entity_id:
            require_canonical_id(self.resolved_entity_id)

    @property
    def normalized_text(self) -> str:
        return normalize_mention(self.original_text)


@dataclass(frozen=True)
class CanonicalEntity:
    entity_id: str
    entity_type: EntityType
    display_name: str
    authority: KnowledgeAuthority
    subtype: str | None = None
    aliases: tuple[EntityAlias, ...] = ()
    mentions: tuple[EntityMention, ...] = ()
    status: str = "active"

    def __post_init__(self) -> None:
        require_canonical_id(self.entity_id)
        if not normalize_mention(self.display_name):
            raise ValueError("entity display name is required")

    @classmethod
    def create(
        cls,
        entity_type: EntityType,
        display_name: str,
        authority: KnowledgeAuthority = KnowledgeAuthority.EXTRACTED,
        *,
        subtype: str | None = None,
        aliases: tuple[EntityAlias, ...] = (),
        mentions: tuple[EntityMention, ...] = (),
    ) -> "CanonicalEntity":
        return cls(
            new_canonical_id(), entity_type, display_name, authority, subtype, aliases, mentions
        )


@dataclass(frozen=True)
class ResolutionCandidate:
    entity_id: str
    entity_type: EntityType
    normalized_aliases: frozenset[str]
    supporting_evidence_ids: frozenset[str]
    supporting_document_version_ids: frozenset[str]

    def __post_init__(self) -> None:
        require_canonical_id(self.entity_id)


@dataclass(frozen=True)
class IdentityResolution:
    mention_id: str
    decision: IdentityDecisionKind
    resolved_entity_id: str | None
    candidate_entity_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class IdentityOperation:
    operation_id: str
    kind: IdentityDecisionKind
    authority: KnowledgeAuthority
    source_entity_ids: tuple[str, ...]
    result_entity_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_canonical_id(self.operation_id)
        for entity_id in (*self.source_entity_ids, *self.result_entity_ids):
            require_canonical_id(entity_id)
        if not self.reason.strip():
            raise ValueError("identity operations require a reason")
