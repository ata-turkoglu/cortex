"""Read-only SQLite projection used by ``canonical.exhaustive``.

Neo4j intentionally has no role in this boundary.  The small interface mirrors
the detached structured-engine reader contract while keeping SQLAlchemy local.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CanonicalEntityRecord,
    EntityMentionRecord,
    GenerationCanonicalMembershipRecord,
    IdentityDecisionRecord,
    OwnershipAssertionRecord,
)
from .graph import (
    CanonicalEntityQueryView,
    CanonicalEvidenceQueryView,
    CanonicalPopulationQueryView,
    CanonicalRelationTargetQueryView,
)


class SQLiteCanonicalReader:
    """Generation-scoped canonical read model; it never writes or repairs rows."""

    def __init__(self, session: Session, workspace_id: str, *, owns_session: bool = False) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.owns_session = owns_session

    def close(self) -> None:
        if self.owns_session:
            self.session.close()

    def query_canonical_population(
        self, generation: str, resource: str, *, safe_limit: int = 500
    ) -> CanonicalPopulationQueryView:
        if resource != "person" or not generation or not 1 <= safe_limit <= 500:
            raise ValueError("SQLite canonical reader supports bounded Person populations")
        ids = tuple(
            self.session.scalars(
                select(GenerationCanonicalMembershipRecord.canonical_entity_id)
                .where(
                    GenerationCanonicalMembershipRecord.workspace_id == self.workspace_id,
                    GenerationCanonicalMembershipRecord.generation_id == generation,
                    GenerationCanonicalMembershipRecord.entity_type == "person",
                )
                .order_by(GenerationCanonicalMembershipRecord.canonical_entity_id)
            )
        )
        selected = ids[:safe_limit]
        return CanonicalPopulationQueryView(
            self.workspace_id,
            generation,
            resource,
            self._entities(generation, selected),
            len(ids),
            len(ids) <= safe_limit,
        )

    def _entities(
        self, generation: str, ids: tuple[str, ...]
    ) -> tuple[CanonicalEntityQueryView, ...]:
        result = []
        for entity_id in ids:
            entity = self.session.get(CanonicalEntityRecord, entity_id)
            if entity is None or entity.workspace_id != self.workspace_id:
                raise ValueError("canonical membership references an out-of-scope Person")
            mentions = (
                self.session.execute(
                    select(EntityMentionRecord)
                    .join(
                        IdentityDecisionRecord,
                        IdentityDecisionRecord.mention_id == EntityMentionRecord.id,
                    )
                    .where(
                        IdentityDecisionRecord.workspace_id == self.workspace_id,
                        IdentityDecisionRecord.canonical_entity_id == entity_id,
                        EntityMentionRecord.generation_id == generation,
                    )
                    .order_by(EntityMentionRecord.id)
                )
                .scalars()
                .all()
            )
            evidence = tuple(_evidence(item, generation) for item in mentions)
            membership = self.session.get(
                GenerationCanonicalMembershipRecord,
                (self.workspace_id, generation, entity_id),
            )
            properties = ()
            if membership and membership.surname and membership.surname_mention_id:
                mention = self.session.get(EntityMentionRecord, membership.surname_mention_id)
                if mention:
                    from .graph import CanonicalEntityPropertyQueryView

                    properties = (
                        CanonicalEntityPropertyQueryView(
                            property_id=f"surname-{mention.id}",
                            key="surname",
                            value=membership.surname,
                            value_type="string",
                            evidence=_evidence(mention, generation),
                        ),
                    )
            result.append(
                CanonicalEntityQueryView(
                    entity.id, entity.entity_type, entity.preferred_name, None, evidence, properties
                )
            )
        return tuple(result)

    def query_canonical_relation_targets(
        self,
        generation: str,
        source_entity_ids: tuple[str, ...],
        relation_type: str,
        *,
        limit: int = 5000,
    ) -> tuple[CanonicalRelationTargetQueryView, ...]:
        if relation_type not in {"owns", "document_supported_ownership"}:
            return ()
        if not generation or not 1 <= limit <= 10_000:
            raise ValueError("generation and relation limit are required")
        rows = (
            self.session.execute(
                select(OwnershipAssertionRecord)
                .where(
                    OwnershipAssertionRecord.workspace_id == self.workspace_id,
                    OwnershipAssertionRecord.generation_id == generation,
                    OwnershipAssertionRecord.person_id.in_(source_entity_ids),
                    OwnershipAssertionRecord.relation_type == "document_supported_ownership",
                )
                .order_by(
                    OwnershipAssertionRecord.person_id,
                    OwnershipAssertionRecord.property_id,
                    OwnershipAssertionRecord.id,
                )
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return tuple(
            CanonicalRelationTargetQueryView(
                row.person_id,
                row.property_id,
                row.id,
                (
                    CanonicalEvidenceQueryView(
                        evidence_id=row.id,
                        document_id=row.document_id,
                        document_version_id=row.document_version_id,
                        logical_document_id=row.logical_document_id or "",
                        chunk_id=row.chunk_id,
                        start_offset=row.span_start,
                        end_offset=row.span_end,
                        source_text=row.source_text,
                        confidence=1.0,
                        generation=generation,
                    ),
                ),
            )
            for row in rows
        )

    def queryable_property_vocabulary(self, generation: str) -> dict[str, frozenset[str]]:
        """Return only governed fields present in this SQLite generation projection."""
        has_surname = self.session.scalar(
            select(GenerationCanonicalMembershipRecord.canonical_entity_id)
            .where(
                GenerationCanonicalMembershipRecord.workspace_id == self.workspace_id,
                GenerationCanonicalMembershipRecord.generation_id == generation,
                GenerationCanonicalMembershipRecord.entity_type == "person",
                GenerationCanonicalMembershipRecord.normalized_surname.is_not(None),
            )
            .limit(1)
        )
        return {"person": frozenset({"surname"})} if has_surname else {}


def _evidence(row: EntityMentionRecord, generation: str) -> CanonicalEvidenceQueryView:
    return CanonicalEvidenceQueryView(
        evidence_id=row.id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        logical_document_id=row.logical_document_id or "",
        chunk_id=row.chunk_id,
        start_offset=row.span_start,
        end_offset=row.span_end,
        source_text=row.source_text,
        confidence=1.0,
        generation=generation,
    )
