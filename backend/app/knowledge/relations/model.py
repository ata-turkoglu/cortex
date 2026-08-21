"""Typed, evidence-supported canonical relation contracts."""

from dataclasses import dataclass
from enum import StrEnum

from ..model import KnowledgeAuthority, require_canonical_id
from ..provenance import ExactSourceProvenance


class RelationSupport(StrEnum):
    EXACT_SPAN = "exact_span"
    DETERMINISTIC_RULE = "deterministic_rule"
    USER_CURATED = "user_curated"


@dataclass(frozen=True)
class CanonicalRelation:
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    authority: KnowledgeAuthority
    generation: str
    support: RelationSupport
    evidence: tuple[ExactSourceProvenance, ...]
    properties: dict[str, object]
    conflicted: bool = False

    def __post_init__(self) -> None:
        for value in (self.relation_id, self.source_entity_id, self.target_entity_id):
            require_canonical_id(value)
        if not self.relation_type.strip() or not self.generation.strip():
            raise ValueError("relation type and generation are required")
        if not self.evidence:
            raise ValueError("canonical relations require exact supporting evidence")
