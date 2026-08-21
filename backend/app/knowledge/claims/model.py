"""Evidence-gated claim, fact, validation, and contradiction contracts."""

from dataclasses import dataclass, replace
from enum import StrEnum

from ..model import KnowledgeAuthority, require_canonical_id
from ..provenance import ExactSourceProvenance


class ClaimStage(StrEnum):
    EXTRACTED = "extracted_claim"
    SUPPORTED = "supported_claim"
    VERIFIED = "verified_fact"


class ValidationOutcome(StrEnum):
    NOT_APPLIED = "not_applied"
    PASSED = "passed"
    FAILED = "failed"
    REVIEWED = "reviewed"


@dataclass(frozen=True)
class ValidatorDecision:
    validator: str
    version: str
    outcome: ValidationOutcome
    reason: str

    @property
    def verifies(self) -> bool:
        return self.outcome in {ValidationOutcome.PASSED, ValidationOutcome.REVIEWED}


@dataclass(frozen=True)
class KnowledgeClaim:
    claim_id: str
    subject_id: str
    predicate: str
    value: object
    stage: ClaimStage
    authority: KnowledgeAuthority
    generation: str
    evidence: tuple[ExactSourceProvenance, ...] = ()
    validator: ValidatorDecision | None = None
    conflicted: bool = False

    def __post_init__(self) -> None:
        require_canonical_id(self.claim_id)
        require_canonical_id(self.subject_id)
        if not self.predicate.strip() or not self.generation.strip():
            raise ValueError("claim predicate and generation are required")
        if self.stage is not ClaimStage.EXTRACTED and not self.evidence:
            raise ValueError("supported claims and verified facts require evidence")
        if self.stage is ClaimStage.VERIFIED and not (
            self.validator and self.validator.verifies
        ):
            raise ValueError("verified facts require an applicable passing validator")

    def support(self, evidence: tuple[ExactSourceProvenance, ...]) -> "KnowledgeClaim":
        if not evidence:
            raise ValueError("support requires source evidence")
        return replace(
            self,
            stage=ClaimStage.SUPPORTED,
            authority=max(self.authority, KnowledgeAuthority.VALIDATED),
            evidence=evidence,
        )

    def verify(self, decision: ValidatorDecision) -> "KnowledgeClaim":
        if self.stage is ClaimStage.EXTRACTED or not self.evidence:
            raise ValueError("a claim must be supported before verification")
        if not decision.verifies:
            raise ValueError("LLM confidence or a failed validator cannot verify a fact")
        return replace(
            self,
            stage=ClaimStage.VERIFIED,
            authority=max(self.authority, KnowledgeAuthority.VALIDATED),
            validator=decision,
        )


@dataclass(frozen=True)
class ClaimConflict:
    left_claim_id: str
    right_claim_id: str
    reason: str


def link_contradiction(left: KnowledgeClaim, right: KnowledgeClaim) -> ClaimConflict:
    if left.subject_id != right.subject_id or left.predicate != right.predicate:
        raise ValueError("only claims about the same subject and predicate can conflict")
    if left.value == right.value:
        raise ValueError("equivalent claim values are not contradictory")
    return ClaimConflict(left.claim_id, right.claim_id, "different supported values")


def preferred_claim(claims: tuple[KnowledgeClaim, ...]) -> KnowledgeClaim | None:
    """Choose only an unambiguous highest-precedence value; never discard conflicts."""
    if not claims:
        return None
    authority = max(claim.authority for claim in claims)
    preferred = tuple(claim for claim in claims if claim.authority == authority)
    values = {repr(claim.value) for claim in preferred}
    return preferred[0] if len(values) == 1 else None
