"""Auditable human adjudication for one exact Person mention."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CanonicalEntityRecord,
    EntityMentionRecord,
    HumanIdentityCurationDecisionRecord,
    IdentityDecisionRecord,
)
from .canonical_core import new_uuid7
from .entities import normalize_mention


def _now() -> datetime:
    return datetime.now(UTC)


def is_population_affecting_person(mention: EntityMentionRecord) -> bool:
    """Current minimal-core population is governed by an exact surname token."""
    tokens = normalize_mention(mention.surface_text).split()
    return mention.entity_type == "person" and len(tokens) >= 2 and tokens[-1] == "merter"


class HumanIdentityCurationStore:
    """Append-only, workspace-scoped curation authority; never performs heuristic links."""

    def __init__(self, session: Session, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def active_for_mention(
        self, mention: EntityMentionRecord
    ) -> HumanIdentityCurationDecisionRecord | None:
        return self.session.scalar(
            select(HumanIdentityCurationDecisionRecord)
            .where(
                HumanIdentityCurationDecisionRecord.workspace_id == self.workspace_id,
                HumanIdentityCurationDecisionRecord.entity_type == mention.entity_type,
                HumanIdentityCurationDecisionRecord.document_id == mention.document_id,
                HumanIdentityCurationDecisionRecord.document_version_id
                == mention.document_version_id,
                HumanIdentityCurationDecisionRecord.logical_document_id
                == mention.logical_document_id,
                HumanIdentityCurationDecisionRecord.chunk_id == mention.chunk_id,
                HumanIdentityCurationDecisionRecord.span_start == mention.span_start,
                HumanIdentityCurationDecisionRecord.span_end == mention.span_end,
                HumanIdentityCurationDecisionRecord.source_text_hash == mention.source_text_hash,
                HumanIdentityCurationDecisionRecord.active.is_(True),
            )
            .order_by(HumanIdentityCurationDecisionRecord.created_at.desc())
        )

    def decide(
        self,
        mention: EntityMentionRecord,
        *,
        action: str,
        canonical_entity_id: str | None,
        reason: str,
        actor: str = "local_curator",
    ) -> HumanIdentityCurationDecisionRecord:
        if mention.workspace_id != self.workspace_id or mention.entity_type != "person":
            raise ValueError("human identity curation requires a workspace Person mention")
        if action not in {"LINK_TO_EXISTING", "KEEP_UNRESOLVED"}:
            raise ValueError("unsupported human identity curation action")
        if not reason.strip() or not actor.strip():
            raise ValueError("human identity curation requires an actor and reason")
        target = None
        if action == "LINK_TO_EXISTING":
            if not canonical_entity_id:
                raise ValueError("LINK_TO_EXISTING requires an explicit canonical Person target")
            target = self.session.get(CanonicalEntityRecord, canonical_entity_id)
            if (
                target is None
                or target.workspace_id != self.workspace_id
                or target.entity_type != "person"
            ):
                raise ValueError("curated target is not a workspace canonical Person")
        elif canonical_entity_id is not None:
            raise ValueError("KEEP_UNRESOLVED cannot select a canonical target")
        previous = self.active_for_mention(mention)
        if previous is not None:
            previous.active = False
        automatic = self.session.scalar(
            select(IdentityDecisionRecord).where(
                IdentityDecisionRecord.workspace_id == self.workspace_id,
                IdentityDecisionRecord.mention_id == mention.id,
            )
        )
        evidence = {
            "mention_id": mention.id,
            "document_id": mention.document_id,
            "document_version_id": mention.document_version_id,
            "logical_document_id": mention.logical_document_id,
            "chunk_id": mention.chunk_id,
            "span_start": mention.span_start,
            "span_end": mention.span_end,
            "source_text_hash": mention.source_text_hash,
            "automatic_decision": automatic.decision if automatic else None,
            "automatic_decision_id": automatic.id if automatic else None,
        }
        row = HumanIdentityCurationDecisionRecord(
            id=new_uuid7(),
            workspace_id=self.workspace_id,
            mention_id=mention.id,
            entity_type=mention.entity_type,
            document_id=mention.document_id,
            document_version_id=mention.document_version_id,
            logical_document_id=mention.logical_document_id,
            chunk_id=mention.chunk_id,
            span_start=mention.span_start,
            span_end=mention.span_end,
            source_text_hash=mention.source_text_hash,
            action=action,
            canonical_entity_id=target.id if target else None,
            actor=actor,
            reason=reason.strip(),
            evidence_reference_json=json.dumps(evidence, sort_keys=True),
            previous_decision_id=previous.id if previous else None,
            active=True,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def history(self, mention_id: str) -> list[HumanIdentityCurationDecisionRecord]:
        return list(
            self.session.scalars(
                select(HumanIdentityCurationDecisionRecord)
                .where(
                    HumanIdentityCurationDecisionRecord.workspace_id == self.workspace_id,
                    HumanIdentityCurationDecisionRecord.mention_id == mention_id,
                )
                .order_by(HumanIdentityCurationDecisionRecord.created_at)
            )
        )
