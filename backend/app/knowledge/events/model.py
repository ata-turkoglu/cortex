"""Canonical events and evidence-bound participant roles."""

from dataclasses import dataclass

from ..model import KnowledgeAuthority, require_canonical_id
from ..provenance import ExactSourceProvenance


@dataclass(frozen=True)
class EventParticipant:
    entity_id: str
    role: str

    def __post_init__(self) -> None:
        require_canonical_id(self.entity_id)
        if not self.role.strip():
            raise ValueError("event participant role is required")


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    event_type: str
    display_name: str
    authority: KnowledgeAuthority
    generation: str
    participants: tuple[EventParticipant, ...]
    evidence: tuple[ExactSourceProvenance, ...]
    temporal_expression_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_id(self.event_id)
        for temporal_id in self.temporal_expression_ids:
            require_canonical_id(temporal_id)
        required = (self.event_type, self.display_name, self.generation)
        if any(not value.strip() for value in required):
            raise ValueError("event type, display name, and generation are required")
        if not self.evidence:
            raise ValueError("canonical events require exact supporting evidence")
