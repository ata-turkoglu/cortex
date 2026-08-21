"""Shared, provider-neutral contracts for canonical Query V2 knowledge."""

from enum import IntEnum, StrEnum
from uuid import UUID, uuid4


class KnowledgeAuthority(IntEnum):
    """Precedence preserved by every canonical persistence adapter."""

    EXTRACTED = 10
    VALIDATED = 20
    USER_CURATED = 30


class UpperOntologyType(StrEnum):
    ENTITY = "entity"
    DOCUMENT = "document"
    LOGICAL_DOCUMENT = "logical_document"
    EVENT = "event"
    TEMPORAL_EXPRESSION = "temporal_expression"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    FACT = "fact"


def new_canonical_id() -> str:
    """Create an opaque identifier independent of names and source text."""
    return str(uuid4())


def require_canonical_id(value: str) -> str:
    try:
        UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("canonical IDs must be opaque UUIDs") from exc
    return value
