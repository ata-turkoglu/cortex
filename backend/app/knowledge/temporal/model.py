"""Temporal expressions that preserve precision and uncertainty."""

from dataclasses import dataclass
from enum import StrEnum

from ..model import require_canonical_id
from ..provenance import ExactSourceProvenance


class TemporalPrecision(StrEnum):
    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TemporalExpression:
    temporal_id: str
    original_text: str
    normalized_start: str | None
    normalized_end: str | None
    semantic_role: str
    precision: TemporalPrecision
    uncertain: bool
    generation: str
    provenance: ExactSourceProvenance

    def __post_init__(self) -> None:
        require_canonical_id(self.temporal_id)
        required = (self.original_text, self.semantic_role, self.generation)
        if any(not value.strip() for value in required):
            raise ValueError("temporal source text, semantic role, and generation are required")
        if self.precision is not TemporalPrecision.UNKNOWN and not self.normalized_start:
            raise ValueError("a normalized temporal value is required for known precision")
        uncertain_precision = {
            TemporalPrecision.APPROXIMATE,
            TemporalPrecision.UNKNOWN,
        }
        if self.precision in uncertain_precision and not self.uncertain:
            raise ValueError("approximate or unknown temporal values must retain uncertainty")
