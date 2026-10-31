"""Minimal SQLite canonical authority; Neo4j is intentionally not consulted here."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    CanonicalEntityRecord,
    CanonicalGenerationChunkRecord,
    CanonicalGenerationStatusRecord,
    CanonicalPropertyRecord,
    EntityMentionRecord,
    GenerationCanonicalMembershipRecord,
    IdentityDecisionRecord,
    OwnershipAssertionRecord,
    RejectedAssertionBlockerRecord,
)
from .entities import canonical_person_display_name, normalize_mention, normalize_person_identity

PROJECTION_VERSION = "minimal-core-v1"


def new_uuid7() -> str:
    """Opaque UUIDv7-compatible ID without adding a dependency."""
    # UUIDv4 is only used for random bits; the version/layout are UUIDv7.
    value = uuid4().int
    timestamp = int(datetime.now(UTC).timestamp() * 1000) & ((1 << 48) - 1)
    value &= (1 << 80) - 1
    value |= timestamp << 80
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    from uuid import UUID

    return str(UUID(int=value))


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _surname_from_person_mention(value: str) -> str | None:
    """A scope hint only; it never resolves or promotes the Person mention."""
    tokens = [item.strip(". ,;:()[]") for item in value.split() if item.strip(". ,;:()[]")]
    while tokens and normalize_mention(tokens[0]) in {
        "bay",
        "bayan",
        "av",
        "dr",
        "prof",
        "sayin",
    }:
        tokens.pop(0)
    if not tokens or len(tokens[-1]) < 2:
        return None
    surname = normalize_mention(tokens[-1])
    return surname if surname and any(character.isalpha() for character in surname) else None


class CanonicalCoreStore:
    """Short-transaction repository for the approved Minimal Canonical Core."""

    def __init__(self, session: Session, workspace_id: str) -> None:
        self.session, self.workspace_id = session, workspace_id

    def persist_person_mention(
        self,
        *,
        generation_id: str,
        document_id: str,
        document_version_id: str,
        logical_document_id: str | None,
        chunk_id: str,
        span_start: int,
        span_end: int,
        source_text: str,
        extractor_version: str,
        extraction_type: str = "entity",
    ) -> EntityMentionRecord:
        if span_start < 0 or span_end <= span_start or len(source_text) != span_end - span_start:
            raise ValueError("mention span must be exact and non-empty")
        existing = self.session.scalar(
            select(EntityMentionRecord).where(
                EntityMentionRecord.workspace_id == self.workspace_id,
                EntityMentionRecord.generation_id == generation_id,
                EntityMentionRecord.chunk_id == chunk_id,
                EntityMentionRecord.span_start == span_start,
                EntityMentionRecord.span_end == span_end,
                EntityMentionRecord.entity_type == "person",
                EntityMentionRecord.extraction_type == extraction_type,
            )
        )
        if existing:
            if existing.source_text_hash != _hash(source_text):
                raise ValueError("conflicting replay for canonical mention")
            return existing
        return self._add_mention(
            generation_id,
            "person",
            source_text,
            document_id,
            document_version_id,
            logical_document_id,
            chunk_id,
            span_start,
            span_end,
            extractor_version,
            extraction_type,
        )

    def persist_property_mention(
        self,
        *,
        generation_id: str,
        document_id: str,
        document_version_id: str,
        logical_document_id: str | None,
        chunk_id: str,
        span_start: int,
        span_end: int,
        source_text: str,
        extractor_version: str,
    ) -> EntityMentionRecord:
        """Persist exact property evidence without treating it as an identity yet."""
        if span_start < 0 or span_end <= span_start or len(source_text) != span_end - span_start:
            raise ValueError("property mention span must be exact and non-empty")
        existing = self.session.scalar(
            select(EntityMentionRecord).where(
                EntityMentionRecord.workspace_id == self.workspace_id,
                EntityMentionRecord.generation_id == generation_id,
                EntityMentionRecord.chunk_id == chunk_id,
                EntityMentionRecord.span_start == span_start,
                EntityMentionRecord.span_end == span_end,
                EntityMentionRecord.entity_type == "asset_property",
                EntityMentionRecord.extraction_type == "entity",
            )
        )
        if existing:
            if existing.source_text_hash != _hash(source_text):
                raise ValueError("conflicting replay for canonical property mention")
            return existing
        return self._add_mention(
            generation_id,
            "asset_property",
            source_text,
            document_id,
            document_version_id,
            logical_document_id,
            chunk_id,
            span_start,
            span_end,
            extractor_version,
            "entity",
        )

    def upsert_property(self, fields: dict[str, str]) -> CanonicalPropertyRecord | None:
        """Create only the conservative, label-bound property identity approved for V2."""
        required = ("province", "district", "neighborhood", "ada", "parsel")
        normalized = {
            key: normalize_mention(value)
            for key, value in fields.items()
            if key
            in {
                "province",
                "district",
                "neighborhood",
                "pafta",
                "ada",
                "parsel",
                "independent_section",
            }
            and isinstance(value, str)
            and normalize_mention(value)
        }
        if any(key not in normalized for key in required):
            return None
        identity_key = json.dumps(
            {key: normalized.get(key) for key in (*required, "pafta", "independent_section")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        existing = self.session.scalar(
            select(CanonicalPropertyRecord).where(
                CanonicalPropertyRecord.workspace_id == self.workspace_id,
                CanonicalPropertyRecord.identity_key == identity_key,
            )
        )
        if existing:
            return existing
        row = CanonicalPropertyRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            property_kind="real_property",
            province=normalized.get("province"),
            district=normalized.get("district"),
            neighborhood=normalized.get("neighborhood"),
            pafta=normalized.get("pafta"),
            ada=normalized.get("ada"),
            parsel=normalized.get("parsel"),
            independent_section=normalized.get("independent_section"),
            identity_key=identity_key,
            identity_strength="strong",
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def persist_ownership_assertion(
        self,
        *,
        generation_id: str,
        person_mention: EntityMentionRecord,
        property_mention: EntityMentionRecord,
        property_record: CanonicalPropertyRecord,
        span_start: int,
        span_end: int,
        source_text: str,
        assertion_rule_version: str,
        share: tuple[int, int] | None = None,
    ) -> OwnershipAssertionRecord:
        decision = self.session.scalar(
            select(IdentityDecisionRecord).where(
                IdentityDecisionRecord.workspace_id == self.workspace_id,
                IdentityDecisionRecord.mention_id == person_mention.id,
                IdentityDecisionRecord.decision.in_(("NEW", "LINK")),
            )
        )
        if decision is None or not decision.canonical_entity_id:
            raise ValueError("ownership requires an accepted person identity")
        if (
            person_mention.generation_id != generation_id
            or property_mention.generation_id != generation_id
            or person_mention.chunk_id != property_mention.chunk_id
            or len(source_text) != span_end - span_start
        ):
            raise ValueError("ownership assertion crosses its exact generation evidence")
        existing = self.session.scalar(
            select(OwnershipAssertionRecord).where(
                OwnershipAssertionRecord.workspace_id == self.workspace_id,
                OwnershipAssertionRecord.generation_id == generation_id,
                OwnershipAssertionRecord.person_mention_id == person_mention.id,
                OwnershipAssertionRecord.property_mention_id == property_mention.id,
                OwnershipAssertionRecord.relation_type == "document_supported_ownership",
            )
        )
        if existing:
            if existing.source_text_hash != _hash(source_text):
                raise ValueError("conflicting replay for ownership assertion")
            return existing
        row = OwnershipAssertionRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            generation_id=generation_id,
            person_id=decision.canonical_entity_id,
            property_id=property_record.id,
            relation_type="document_supported_ownership",
            person_mention_id=person_mention.id,
            property_mention_id=property_mention.id,
            document_id=person_mention.document_id,
            document_version_id=person_mention.document_version_id,
            logical_document_id=person_mention.logical_document_id,
            chunk_id=person_mention.chunk_id,
            span_start=span_start,
            span_end=span_end,
            source_text=source_text,
            source_text_hash=_hash(source_text),
            share_numerator=share[0] if share else None,
            share_denominator=share[1] if share else None,
            recorded_date=None,
            assertion_rule_version=assertion_rule_version,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def persist_rejected_ownership_blocker(
        self,
        *,
        generation_id: str,
        person_mention: EntityMentionRecord,
        span_start: int,
        span_end: int,
        source_text: str,
        reason: str,
    ) -> RejectedAssertionBlockerRecord:
        """Persist rejected evidence without creating identity, property, or ownership truth."""
        if (
            person_mention.generation_id != generation_id
            or len(source_text) != span_end - span_start
        ):
            raise ValueError("rejected ownership blocker crosses its exact generation evidence")
        existing = self.session.scalar(
            select(RejectedAssertionBlockerRecord).where(
                RejectedAssertionBlockerRecord.workspace_id == self.workspace_id,
                RejectedAssertionBlockerRecord.generation_id == generation_id,
                RejectedAssertionBlockerRecord.chunk_id == person_mention.chunk_id,
                RejectedAssertionBlockerRecord.span_start == span_start,
                RejectedAssertionBlockerRecord.span_end == span_end,
                RejectedAssertionBlockerRecord.reason == reason,
            )
        )
        if existing:
            if existing.source_text_hash != _hash(source_text):
                raise ValueError("conflicting replay for rejected ownership blocker")
            return existing
        surname = _surname_from_person_mention(person_mention.surface_text)
        row = RejectedAssertionBlockerRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            generation_id=generation_id,
            blocker_type="rejected_assertion",
            entity_type="person",
            relation_type="owns",
            potentially_countable=True,
            affected_dimension="property_count",
            normalized_subject_surname=surname,
            document_id=person_mention.document_id,
            document_version_id=person_mention.document_version_id,
            logical_document_id=person_mention.logical_document_id,
            chunk_id=person_mention.chunk_id,
            span_start=span_start,
            span_end=span_end,
            source_text=source_text,
            source_text_hash=_hash(source_text),
            reason=reason,
            scope_hints_json=json.dumps(
                {
                    "subject_entity_type": "person",
                    "subject_surname": surname,
                    "relation_type": "owns",
                    "affected_dimension": "property_count",
                }
            ),
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def record_chunk(
        self, generation_id: str, chunk_id: str, content_hash: str, *, failed: str | None = None
    ) -> None:
        row = self.session.scalar(
            select(CanonicalGenerationChunkRecord).where(
                CanonicalGenerationChunkRecord.workspace_id == self.workspace_id,
                CanonicalGenerationChunkRecord.generation_id == generation_id,
                CanonicalGenerationChunkRecord.chunk_id == chunk_id,
            )
        )
        status = "failed" if failed else "processed"
        if row:
            if row.content_hash != content_hash:
                raise ValueError("conflicting canonical manifest chunk replay")
            # A failed construction attempt may be retried with corrected
            # extraction evidence.  The immutable manifest content remains the
            # same; replace only its accounting outcome so READY reflects the
            # successful retry rather than a stale failure.
            if row.status == "failed" and status == "processed":
                row.status = "processed"
                row.failure_reason = None
                row.processed_at = _now()
                self.session.flush()
                return
            if row.status != status:
                raise ValueError("conflicting canonical manifest chunk replay")
            return
        self.session.add(
            CanonicalGenerationChunkRecord(
                id=new_uuid7(),
                workspace_id=self.workspace_id,
                generation_id=generation_id,
                chunk_id=chunk_id,
                content_hash=content_hash,
                status=status,
                failure_reason=failed,
                processed_at=_now(),
            )
        )
        self.session.flush()

    def _add_mention(
        self,
        generation_id,
        entity_type,
        source_text,
        document_id,
        document_version_id,
        logical_document_id,
        chunk_id,
        start,
        end,
        extractor_version,
        extraction_type,
    ):
        row = EntityMentionRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            generation_id=generation_id,
            entity_type=entity_type,
            surface_text=source_text,
            normalized_text=normalize_mention(source_text),
            document_id=document_id,
            document_version_id=document_version_id,
            logical_document_id=logical_document_id,
            chunk_id=chunk_id,
            span_start=start,
            span_end=end,
            source_text=source_text,
            source_text_hash=_hash(source_text),
            extraction_type=extraction_type,
            extractor_version=extractor_version,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def decide_person(
        self,
        mention: EntityMentionRecord,
        *,
        candidate_ids: tuple[str, ...] = (),
        candidate_provenance: str | None = None,
        resolver_version: str = "minimal-core-v1",
        policy_version: str = "minimal-core-v1",
    ) -> IdentityDecisionRecord:
        existing = self.session.scalar(
            select(IdentityDecisionRecord).where(
                IdentityDecisionRecord.workspace_id == self.workspace_id,
                IdentityDecisionRecord.mention_id == mention.id,
            )
        )
        if existing:
            return existing
        normalized = normalize_person_identity(mention.surface_text)
        candidates = tuple(sorted(set(candidate_ids)))
        target = None
        decision = "UNRESOLVED"
        basis = "insufficient identity evidence"
        # A matching human record is keyed to this exact source evidence, not
        # normalized text. It is therefore a distinct authority from the
        # automatic resolver and cannot teach a future name heuristic.
        from .identity_curation import HumanIdentityCurationStore

        curation = HumanIdentityCurationStore(self.session, self.workspace_id)
        curated = curation.active_for_mention(mention)
        if curated is not None:
            if curated.action == "LINK_TO_EXISTING":
                target = self.session.get(CanonicalEntityRecord, curated.canonical_entity_id)
                if target is None or target.workspace_id != self.workspace_id:
                    raise ValueError("curated identity target is no longer a workspace Person")
                decision = "LINK"
                basis = f"explicit human curation decision {curated.id}"
            else:
                basis = f"explicit human keep-unresolved decision {curated.id}"
        if candidate_ids and not candidate_provenance:
            raise ValueError("identity candidate provenance is required")
        if normalized and curated is None:
            # A link requires a caller-provided unique candidate that exists in SQLite;
            # similarity and same-name discovery never supply it implicitly.
            if len(candidates) == 1:
                target = self.session.get(CanonicalEntityRecord, candidates[0])
                if (
                    target is None
                    or target.workspace_id != self.workspace_id
                    or target.entity_type != "person"
                ):
                    raise ValueError("LINK target is not a durable workspace canonical Person")
                decision, basis = "LINK", "unique externally corroborated deterministic candidate"
            elif not candidates:
                display = canonical_person_display_name(mention.surface_text)
                if display:
                    target = CanonicalEntityRecord(
                        id=new_uuid7(),
                        workspace_id=self.workspace_id,
                        entity_type="person",
                        preferred_name=display,
                        normalized_preferred_name=normalized,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                    self.session.add(target)
                    self.session.flush()
                    decision, basis = "NEW", "first safe complete-name mention"
        row = IdentityDecisionRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            mention_id=mention.id,
            decision=decision,
            canonical_entity_id=target.id if target else None,
            decision_basis_json=json.dumps(
                {"reason": basis, "candidate_provenance": candidate_provenance}, sort_keys=True
            ),
            candidate_entity_ids_json=json.dumps(candidates),
            resolver_version=resolver_version,
            policy_version=policy_version,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def rebuild_membership(self, generation_id: str) -> int:
        self.session.execute(
            delete(GenerationCanonicalMembershipRecord).where(
                GenerationCanonicalMembershipRecord.workspace_id == self.workspace_id,
                GenerationCanonicalMembershipRecord.generation_id == generation_id,
            )
        )
        accepted = self.session.execute(
            select(
                IdentityDecisionRecord.canonical_entity_id,
                func.min(EntityMentionRecord.id),
                func.min(EntityMentionRecord.surface_text),
            )
            .join(EntityMentionRecord)
            .where(
                IdentityDecisionRecord.workspace_id == self.workspace_id,
                EntityMentionRecord.generation_id == generation_id,
                IdentityDecisionRecord.decision.in_(("NEW", "LINK")),
            )
            .group_by(IdentityDecisionRecord.canonical_entity_id)
        ).all()
        for entity_id, mention_id, source_text in accepted:
            surname = _governed_surname(source_text)
            self.session.add(
                GenerationCanonicalMembershipRecord(
                    workspace_id=self.workspace_id,
                    generation_id=generation_id,
                    canonical_entity_id=entity_id,
                    entity_type="person",
                    surname=surname,
                    normalized_surname=normalize_mention(surname) if surname else None,
                    surname_mention_id=mention_id if surname else None,
                    membership_basis_mention_id=mention_id,
                    created_at=_now(),
                )
            )
        self.session.flush()
        return len(accepted)

    def consolidate_exact_person_identities(self, generation_id: str) -> dict[str, str]:
        """Link exact-name identities only after cross-document corroboration.

        Extraction frequently sees the same full name in multiple chunks.  A
        mention is not a person: separate NEW decisions must not inflate a
        generation population.  Conversely, a same-name occurrence in just one
        document version may still be a homonym, so it remains separate until
        exact normalized identity is corroborated by a second version.
        """
        rows = self.session.execute(
            select(IdentityDecisionRecord, EntityMentionRecord, CanonicalEntityRecord)
            .join(EntityMentionRecord, IdentityDecisionRecord.mention_id == EntityMentionRecord.id)
            .join(
                CanonicalEntityRecord,
                IdentityDecisionRecord.canonical_entity_id == CanonicalEntityRecord.id,
            )
            .where(
                IdentityDecisionRecord.workspace_id == self.workspace_id,
                EntityMentionRecord.generation_id == generation_id,
                IdentityDecisionRecord.decision.in_(("NEW", "LINK")),
                CanonicalEntityRecord.entity_type == "person",
            )
        ).all()
        groups: dict[
            str, list[tuple[IdentityDecisionRecord, EntityMentionRecord, CanonicalEntityRecord]]
        ] = {}
        for decision, mention, entity in rows:
            key = entity.normalized_preferred_name
            if key:
                groups.setdefault(key, []).append((decision, mention, entity))
        remapped: dict[str, str] = {}
        for entries in groups.values():
            if len({mention.document_version_id for _, mention, _ in entries}) < 2:
                continue
            target_id = min(entity.id for _, _, entity in entries)
            for decision, _, entity in entries:
                if entity.id == target_id:
                    continue
                decision.canonical_entity_id = target_id
                decision.decision = "LINK"
                decision.decision_basis_json = json.dumps(
                    {"reason": "exact normalized identity corroborated across document versions"},
                    sort_keys=True,
                )
                remapped[decision.mention_id] = target_id
        self.session.flush()
        return remapped

    def record_status(
        self,
        *,
        generation_id: str,
        manifest_hash: str,
        manifest_chunk_count: int,
        processed_chunk_count: int | None = None,
        failed_chunk_count: int | None = None,
        rejected_assertion_count: int = 0,
    ) -> CanonicalGenerationStatusRecord:
        mentions = (
            self.session.scalar(
                select(func.count())
                .select_from(EntityMentionRecord)
                .where(
                    EntityMentionRecord.workspace_id == self.workspace_id,
                    EntityMentionRecord.generation_id == generation_id,
                )
            )
            or 0
        )
        resolved = (
            self.session.scalar(
                select(func.count())
                .select_from(IdentityDecisionRecord)
                .join(EntityMentionRecord)
                .where(
                    IdentityDecisionRecord.workspace_id == self.workspace_id,
                    EntityMentionRecord.generation_id == generation_id,
                    IdentityDecisionRecord.decision.in_(("NEW", "LINK")),
                )
            )
            or 0
        )
        unresolved = (
            self.session.scalar(
                select(func.count())
                .select_from(IdentityDecisionRecord)
                .join(EntityMentionRecord)
                .where(
                    IdentityDecisionRecord.workspace_id == self.workspace_id,
                    EntityMentionRecord.generation_id == generation_id,
                    IdentityDecisionRecord.decision == "UNRESOLVED",
                )
            )
            or 0
        )
        members = self.rebuild_membership(generation_id)
        persisted_processed = (
            self.session.scalar(
                select(func.count())
                .select_from(CanonicalGenerationChunkRecord)
                .where(
                    CanonicalGenerationChunkRecord.workspace_id == self.workspace_id,
                    CanonicalGenerationChunkRecord.generation_id == generation_id,
                    CanonicalGenerationChunkRecord.status == "processed",
                )
            )
            or 0
        )
        persisted_failed = (
            self.session.scalar(
                select(func.count())
                .select_from(CanonicalGenerationChunkRecord)
                .where(
                    CanonicalGenerationChunkRecord.workspace_id == self.workspace_id,
                    CanonicalGenerationChunkRecord.generation_id == generation_id,
                    CanonicalGenerationChunkRecord.status == "failed",
                )
            )
            or 0
        )
        if processed_chunk_count is not None and processed_chunk_count != persisted_processed:
            raise ValueError(
                "canonical processed count must come from persisted manifest accounting"
            )
        if failed_chunk_count is not None and failed_chunk_count != persisted_failed:
            raise ValueError("canonical failed count must come from persisted manifest accounting")
        assertions = (
            self.session.scalar(
                select(func.count())
                .select_from(OwnershipAssertionRecord)
                .where(
                    OwnershipAssertionRecord.workspace_id == self.workspace_id,
                    OwnershipAssertionRecord.generation_id == generation_id,
                )
            )
            or 0
        )
        safe_properties = (
            self.session.scalar(
                select(func.count(func.distinct(OwnershipAssertionRecord.property_id))).where(
                    OwnershipAssertionRecord.workspace_id == self.workspace_id,
                    OwnershipAssertionRecord.generation_id == generation_id,
                )
            )
            or 0
        )
        status = (
            "FAILED"
            if persisted_failed
            else (
                "READY"
                if persisted_processed == manifest_chunk_count
                and not unresolved
                and not rejected_assertion_count
                else "PARTIAL"
            )
        )
        row = self.session.get(
            CanonicalGenerationStatusRecord, (self.workspace_id, generation_id, PROJECTION_VERSION)
        )
        values = dict(
            status=status,
            manifest_hash=manifest_hash,
            manifest_chunk_count=manifest_chunk_count,
            processed_chunk_count=persisted_processed,
            mention_count=mentions,
            resolved_mention_count=resolved,
            unresolved_mention_count=unresolved,
            safe_property_count=safe_properties,
            assertion_count=assertions,
            rejected_assertion_count=rejected_assertion_count,
            failed_chunk_count=persisted_failed,
            projection_row_count=members,
            failure_reason_json=(
                json.dumps({"reason": "one or more manifest chunks failed"})
                if persisted_failed
                else None
            ),
            completed_at=_now(),
            updated_at=_now(),
        )
        if row is None:
            row = CanonicalGenerationStatusRecord(
                workspace_id=self.workspace_id,
                generation_id=generation_id,
                projection_version=PROJECTION_VERSION,
                **values,
            )
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self.session.flush()
        return row

    def ranked_people_by_surname(self, generation_id: str, surname: str) -> list[tuple[str, int]]:
        """Read-only authoritative SQL projection preserving zero-count members."""
        normalized = normalize_mention(surname)
        rows = self.session.execute(
            select(
                CanonicalEntityRecord.preferred_name,
                func.count(func.distinct(OwnershipAssertionRecord.property_id)).label(
                    "property_count"
                ),
            )
            .join(
                GenerationCanonicalMembershipRecord,
                GenerationCanonicalMembershipRecord.canonical_entity_id == CanonicalEntityRecord.id,
            )
            .outerjoin(
                OwnershipAssertionRecord,
                (OwnershipAssertionRecord.person_id == CanonicalEntityRecord.id)
                & (OwnershipAssertionRecord.workspace_id == self.workspace_id)
                & (OwnershipAssertionRecord.generation_id == generation_id),
            )
            .where(
                GenerationCanonicalMembershipRecord.workspace_id == self.workspace_id,
                GenerationCanonicalMembershipRecord.generation_id == generation_id,
                GenerationCanonicalMembershipRecord.normalized_surname == normalized,
            )
            .group_by(CanonicalEntityRecord.id)
            .order_by(
                func.count(func.distinct(OwnershipAssertionRecord.property_id)).desc(),
                CanonicalEntityRecord.preferred_name.asc(),
                CanonicalEntityRecord.id.asc(),
            )
        ).all()
        return [(name, int(count)) for name, count in rows]


def _governed_surname(source_text: str) -> str | None:
    """Conservative single-token surname derivation performed during construction."""
    display = canonical_person_display_name(source_text)
    if not display:
        return None
    parts = display.split()
    return parts[-1] if len(parts) == 2 else None
