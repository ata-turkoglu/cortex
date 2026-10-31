"""Query-scoped completeness over the SQLite canonical authority.

This classifies uncertainty evidence; it never resolves identity or promotes a
rejected assertion into canonical knowledge.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.canonical_core import PROJECTION_VERSION
from app.knowledge.entities import normalize_mention
from app.models import (
    CanonicalGenerationStatusRecord,
    EntityMentionRecord,
    IdentityDecisionRecord,
    RejectedAssertionBlockerRecord,
)
from app.query.ir.schemas import (
    CountNode,
    FilterNode,
    LogicalQueryIR,
    RankNode,
    RelationAggregateNode,
)
from app.query.orchestration import CompletenessEvidenceRef, QueryCompleteness


class CanonicalCompletenessEvaluator:
    """Evaluate Person-identity blockers against the query's population scope."""

    def __init__(self, session: Session, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def evaluate(
        self, generation_id: str, ir: LogicalQueryIR, *, known_count: int | None
    ) -> QueryCompleteness:
        surname = _surname_scope(ir)
        blockers = tuple(
            self.session.execute(
                select(EntityMentionRecord)
                .join(
                    IdentityDecisionRecord,
                    IdentityDecisionRecord.mention_id == EntityMentionRecord.id,
                )
                .where(
                    EntityMentionRecord.workspace_id == self.workspace_id,
                    EntityMentionRecord.generation_id == generation_id,
                    EntityMentionRecord.entity_type == "person",
                    IdentityDecisionRecord.workspace_id == self.workspace_id,
                    IdentityDecisionRecord.decision == "UNRESOLVED",
                )
                .order_by(EntityMentionRecord.id)
            ).scalars()
        )
        relevant = (
            blockers
            if surname is None
            else tuple(item for item in blockers if _governed_surname(item.surface_text) == surname)
        )
        rejected = (
            tuple(
                self.session.scalars(
                    select(RejectedAssertionBlockerRecord)
                    .where(
                        RejectedAssertionBlockerRecord.workspace_id == self.workspace_id,
                        RejectedAssertionBlockerRecord.generation_id == generation_id,
                        RejectedAssertionBlockerRecord.potentially_countable.is_(True),
                        RejectedAssertionBlockerRecord.normalized_subject_surname == surname,
                    )
                    .order_by(RejectedAssertionBlockerRecord.id)
                )
            )
            if any(isinstance(node, RelationAggregateNode) for node in ir.nodes)
            else ()
        )
        legacy_rejected = _legacy_rejection_applies(
            self.session, self.workspace_id, generation_id, ir, rejected
        )
        dimensions = _affected_dimensions(ir, bool(relevant), bool(rejected), legacy_rejected)
        refs = tuple(
            CompletenessEvidenceRef(
                evidence_id=item.id,
                kind="unresolved_person",
                raw_text=item.surface_text,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                logical_document_id=item.logical_document_id,
                chunk_id=item.chunk_id,
                start_offset=item.span_start,
                end_offset=item.span_end,
            )
            for item in relevant
        ) + tuple(
            CompletenessEvidenceRef(
                evidence_id=item.id,
                kind="rejected_assertion",
                raw_text=item.source_text,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                logical_document_id=item.logical_document_id,
                chunk_id=item.chunk_id,
                start_offset=item.span_start,
                end_offset=item.span_end,
                reason=item.reason,
            )
            for item in rejected
        )
        scope = f"Person surname = {surname}" if surname else "all Persons in the active corpus"
        if not relevant and not rejected and not legacy_rejected:
            return QueryCompleteness(
                status="COMPLETE",
                scope=scope,
                known_count=known_count,
                min_count=known_count,
            )
        reasons = []
        if relevant:
            reasons.append(
                "Unresolved Person evidence may change the canonical population."
                if surname is None
                else (
                    "Unresolved Person evidence explicitly carries the governed surname "
                    "and may change the canonical population."
                )
            )
        if rejected:
            reasons.append(
                "Rejected ownership evidence may change the scoped property-count metric."
            )
        if legacy_rejected:
            reasons.append(
                "Legacy aggregate rejected-assertion accounting has no scope provenance; "
                "it may affect this ownership ranking metric."
            )
        return QueryCompleteness(
            status="PARTIAL",
            scope=scope,
            reasons=tuple(reasons),
            relevant_unresolved_count=len(relevant),
            relevant_rejected_assertion_count=len(rejected) + int(legacy_rejected),
            affected_dimensions=dimensions,
            evidence_refs=refs,
            known_count=known_count,
            min_count=known_count,
            additional_population_possible=bool(relevant),
        )


def _surname_scope(ir: LogicalQueryIR) -> str | None:
    for node in ir.nodes:
        if (
            isinstance(node, FilterNode)
            and node.field.resource == "person"
            and node.field.field == "surname"
            and node.comparator == "eq"
            and isinstance(node.value, str)
        ):
            value = normalize_mention(node.value)
            if value:
                return value
    return None


def _governed_surname(raw_text: str) -> str | None:
    """Extract an explicit terminal surname without treating initials as scope evidence."""
    tokens = [token for token in re.split(r"\s+", raw_text.strip()) if token]
    while tokens and normalize_mention(tokens[0].strip(". ,;:")) in {
        "bay",
        "bayan",
        "av",
        "dr",
        "prof",
        "sayin",
        "sayın",
    }:
        tokens.pop(0)
    while tokens and normalize_mention(tokens[-1].strip(". ,;:")) in {"bey", "hanim", "hanım"}:
        tokens.pop()
    if not tokens:
        return None
    candidate = tokens[-1].strip(". ,;:()[]")
    if len(candidate) < 2 or not any(character.isalpha() for character in candidate):
        return None
    return normalize_mention(candidate)


def _legacy_rejection_applies(
    session: Session,
    workspace_id: str,
    generation_id: str,
    ir: LogicalQueryIR,
    rejected,
) -> bool:
    """Old generations retained only a count; confine that uncertainty to ownership metrics."""
    if rejected or not any(isinstance(node, RelationAggregateNode) for node in ir.nodes):
        return False
    status = session.get(
        CanonicalGenerationStatusRecord,
        (workspace_id, generation_id, PROJECTION_VERSION),
    )
    return bool(status and status.rejected_assertion_count)


def _affected_dimensions(
    ir: LogicalQueryIR,
    population_blocked: bool,
    rejected_metric_blocked: bool,
    legacy_metric_blocked: bool,
) -> tuple[str, ...]:
    if not (population_blocked or rejected_metric_blocked or legacy_metric_blocked):
        return ()
    dimensions = ["population"] if population_blocked else []
    if population_blocked and any(isinstance(node, CountNode) for node in ir.nodes):
        dimensions.append("count")
    if population_blocked and any(
        isinstance(node, RankNode | RelationAggregateNode) for node in ir.nodes
    ):
        dimensions.append("ranking")
    if (rejected_metric_blocked or legacy_metric_blocked) and any(
        isinstance(node, RelationAggregateNode) for node in ir.nodes
    ):
        dimensions.extend(("property_count", "ranking"))
    return tuple(dict.fromkeys(dimensions))
