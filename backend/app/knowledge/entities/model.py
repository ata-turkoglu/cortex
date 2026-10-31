"""Canonical entities, mentions, aliases, and reversible identity decisions."""

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from ..model import KnowledgeAuthority, new_canonical_id, require_canonical_id
from ..provenance import ExactSourceProvenance


def normalize_mention(value: str) -> str:
    # Treat Turkish dotted/dotless-I variants as one comparison key.  The
    # original text remains untouched for display and exact provenance.
    value = value.translate(str.maketrans({"I": "i", "\u0130": "i", "\u0131": "i"}))
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


_PERSON_TITLES = frozenset({
    "av", "av.", "dr", "dr.", "prof", "prof.", "bay", "bayan", "bey", "hanım", "hanim",
    "sayın", "sayin",
})
_PERSON_CONTEXT_PREFIXES = frozenset({"varisleri", "varisi", "mirasçıları", "mirascilari"})


_PERSON_NAME_TOKEN = re.compile(r"^[^\W\d_]+(?:-[^\W\d_]+)*$", re.UNICODE)


def normalize_person_identity(value: str) -> str | None:
    """Return a comparison-only person identity, preserving the original mention elsewhere."""
    value = unicodedata.normalize("NFKC", value).strip()
    # A canonical Person is a name, not a legal clause, property description,
    # identifier, or possessive phrase. These source spans remain auditable but
    # cannot safely become automatic canonical identities.
    if any(character.isdigit() or character in "'â€™" for character in value):
        return None
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[\[\],;:]+", " ", value)
    tokens = [token.strip(". ") for token in value.split()]
    while tokens and normalize_mention(tokens[0]) in _PERSON_TITLES | _PERSON_CONTEXT_PREFIXES:
        tokens.pop(0)
    # Turkish courtesy titles can appear after a given name (for example,
    # ``Ali Bey``). They do not make a one-token reference identifiable.
    while tokens and normalize_mention(tokens[-1]) in _PERSON_TITLES:
        tokens.pop()
    tokens = [token for token in tokens if token]
    # A one-token surname, title, initial, or OCR fragment is not enough evidence
    # to create an extracted canonical person.
    if (
        not 2 <= len(tokens) <= 5
        or any(len(token) == 1 for token in tokens)
        or any(not _PERSON_NAME_TOKEN.fullmatch(token) for token in tokens)
        or any(not (token.isupper() or token[0].isupper()) for token in tokens)
    ):
        return None
    return normalize_mention(" ".join(tokens))


def canonical_person_display_name(value: str) -> str | None:
    """Produce a display candidate without titles/context prefixes or parenthetical aliases."""
    identity = normalize_person_identity(value)
    if identity is None:
        return None
    value = re.sub(r"\([^)]*\)", " ", unicodedata.normalize("NFKC", value)).strip()
    tokens = [token.strip(". ") for token in re.sub(r"[\[\],;:]+", " ", value).split()]
    while tokens and normalize_mention(tokens[0]) in _PERSON_TITLES | _PERSON_CONTEXT_PREFIXES:
        tokens.pop(0)
    while tokens and normalize_mention(tokens[-1]) in _PERSON_TITLES:
        tokens.pop()
    return " ".join(token for token in tokens if token) or None


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    ASSET_PROPERTY = "asset_property"
    DYNAMIC = "dynamic"


class EntityPropertyValueType(StrEnum):
    """The closed value types permitted in canonical entity properties."""

    STRING = "string"


@dataclass(frozen=True)
class EntityPropertyDefinition:
    """A governed, queryable property -- never an arbitrary graph field."""

    key: str
    entity_types: frozenset[EntityType]
    value_type: EntityPropertyValueType
    operators: frozenset[str]
    queryable: bool = True


ENTITY_PROPERTY_VOCABULARY: dict[str, EntityPropertyDefinition] = {
    "surname": EntityPropertyDefinition(
        key="surname",
        entity_types=frozenset({EntityType.PERSON}),
        value_type=EntityPropertyValueType.STRING,
        operators=frozenset({"eq"}),
    )
}


@dataclass(frozen=True)
class CanonicalEntityProperty:
    """One resolved, generation-bound property assertion with exact evidence."""

    property_id: str
    entity_id: str
    key: str
    value: str
    value_type: EntityPropertyValueType
    authority: KnowledgeAuthority
    generation: str
    provenance: ExactSourceProvenance
    status: str = "resolved"

    def __post_init__(self) -> None:
        require_canonical_id(self.property_id)
        require_canonical_id(self.entity_id)
        definition = ENTITY_PROPERTY_VOCABULARY.get(self.key)
        if definition is None or not definition.queryable:
            raise ValueError("entity property key is not governed and queryable")
        if self.value_type != definition.value_type or not self.value.strip():
            raise ValueError("entity property value does not match its governed definition")
        if not self.generation.strip() or self.provenance.generation != self.generation:
            raise ValueError("entity property provenance must match its generation")
        if self.status not in {"candidate", "conflicted", "resolved"}:
            raise ValueError("entity property status is unsupported")

    @property
    def queryable(self) -> bool:
        return self.status == "resolved"

    @property
    def normalized_value(self) -> str:
        return normalize_mention(self.value)


class IdentityDecisionKind(StrEnum):
    UNRESOLVED = "unresolved"
    NEW_CANONICAL = "new_canonical"
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
