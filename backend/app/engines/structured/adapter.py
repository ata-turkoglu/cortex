"""Canonical graph population adapter for the detached structured engine."""

from __future__ import annotations

from typing import Protocol

from app.knowledge.graph import CanonicalPopulationQueryView
from app.query.orchestration import ExactEvidenceSpan

from .schemas import CanonicalPopulation, CanonicalRecord


class CanonicalPopulationReader(Protocol):
    workspace_id: str

    def query_canonical_population(
        self, generation: str, resource: str, *, safe_limit: int = 500
    ) -> CanonicalPopulationQueryView: ...


def load_canonical_population(
    reader: CanonicalPopulationReader,
    generation_id: str,
    resource: str,
    *,
    safe_limit: int = 500,
) -> CanonicalPopulation:
    view = reader.query_canonical_population(
        generation_id, resource, safe_limit=safe_limit
    )
    if view.workspace_id != reader.workspace_id or view.generation != generation_id:
        raise ValueError("canonical population reader returned a crossed scope")
    records = tuple(
        CanonicalRecord(
            record_id=entity.entity_id,
            resource=resource,
            values={
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "display_name": entity.display_name,
                "subtype": entity.subtype,
            },
            evidence=tuple(
                ExactEvidenceSpan(
                    evidence_id=item.evidence_id,
                    workspace_id=view.workspace_id,
                    document_id=item.document_id,
                    document_version_id=item.document_version_id,
                    logical_document_id=item.logical_document_id,
                    chunk_id=item.chunk_id,
                    start_offset=item.start_offset,
                    end_offset=item.end_offset,
                    source_text=item.source_text,
                    generation_id=item.generation,
                    relevance_score=item.confidence,
                    quality_score=item.confidence,
                )
                for item in entity.evidence
            ),
        )
        for entity in view.entities
        if entity.evidence
    )
    unresolved = () if view.safely_enumerable else ("population-beyond-safe-limit",)
    return CanonicalPopulation(
        workspace_id=view.workspace_id,
        generation_id=view.generation,
        resource=view.resource,
        boundary=f"all active canonical {view.resource} records",
        records=records,
        candidate_count=view.candidate_count,
        unresolved_candidate_ids=unresolved,
        safely_enumerable=view.safely_enumerable and len(records) == view.candidate_count,
        ready_projections=("canonical_entities",),
    )
