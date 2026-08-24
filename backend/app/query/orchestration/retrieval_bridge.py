"""Generation-bound retrieval normalization for the active V2 runtime."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ...retrieval.hybrid import reciprocal_rank_fusion
from ...retrieval.schemas import Evidence
from ..execution import V2ExecutionResult
from ..planning import PhysicalExecutionPlan
from ..scope import GenerationScope
from .schemas import (
    CompletenessReport,
    EngineResult,
    EngineTrace,
    ExactEvidenceSpan,
    GroundedItem,
    ProvenanceLink,
    TrustedSource,
)


class RetrievalBridgeIntegrityError(ValueError):
    """Raw projection evidence cannot be bound to the immutable source snapshot."""


@dataclass(frozen=True)
class RetrievalBridgeResult:
    engine_result: EngineResult
    fused_count: int


def bridge_retrieval(
    plan: PhysicalExecutionPlan,
    execution: V2ExecutionResult,
    scope: GenerationScope,
    trusted_sources: tuple[TrustedSource, ...],
    *,
    limit: int,
) -> RetrievalBridgeResult:
    """RRF-fuse raw reads and bind every result to an authoritative chunk.

    The manifest is the authority.  Projection evidence is accepted only when
    all immutable identities and complete content agree with that source.
    """
    if execution.trace.workspace_id != scope.workspace_id or (
        execution.trace.generation_id != scope.generation_id
    ):
        raise RetrievalBridgeIntegrityError("execution trace crosses immutable generation scope")
    if any(
        source.workspace_id != scope.workspace_id or source.generation_id != scope.generation_id
        for source in trusted_sources
    ):
        raise RetrievalBridgeIntegrityError("trusted sources cross immutable generation scope")
    retrieval_steps = tuple(
        step for step in (plan.graph.steps if plan.graph else ()) if step.engine == "retrieval"
    )
    if len(retrieval_steps) != 1:
        raise RetrievalBridgeIntegrityError("plan must declare exactly one retrieval step")
    step = retrieval_steps[0]
    fused = reciprocal_rank_fusion(
        list(execution.dense_evidence), list(execution.sparse_evidence), limit=limit
    )
    source_by_chunk = {source.chunk_id: source for source in trusted_sources}
    if len(source_by_chunk) != len(trusted_sources):
        raise RetrievalBridgeIntegrityError("trusted source binding is ambiguous")
    spans: list[ExactEvidenceSpan] = []
    rows: list[GroundedItem] = []
    links: list[ProvenanceLink] = []
    for rank, item in enumerate(fused, start=1):
        source = source_by_chunk.get(item.chunk_id or "")
        _validate_projection_evidence(item, source, scope)
        evidence_id = f"retrieval-{scope.generation_id[:12]}-{rank}"
        span = ExactEvidenceSpan(
            evidence_id=evidence_id,
            workspace_id=scope.workspace_id,
            document_id=source.document_id,
            document_version_id=source.document_version_id,
            logical_document_id=source.logical_document_id,
            chunk_id=source.chunk_id,
            start_offset=0,
            end_offset=len(source.content),
            source_text=source.content,
            generation_id=scope.generation_id,
            relevance_score=max(0.0, min(1.0, item.score)),
            quality_score=1.0,
        )
        spans.append(span)
        row_id = f"retrieval-row-{rank}"
        rows.append(
            GroundedItem(
                item_id=row_id,
                values={"evidence": source.content, "fusion_rank": rank},
                evidence_ids=(evidence_id,),
            )
        )
        links.append(ProvenanceLink(result_id=row_id, evidence_ids=(evidence_id,)))
    state = "success" if spans else "unsupported"
    result = EngineResult(
        result_id=f"retrieval-result-{scope.generation_id[:12]}",
        workspace_id=scope.workspace_id,
        generation_id=scope.generation_id,
        step_id=step.step_id,
        engine=step.engine,
        capability=step.capability,
        state=state,
        structured_rows=tuple(rows),
        text_evidence=tuple(spans),
        provenance=tuple(links),
        completeness=CompletenessReport(coverage="grounded", state="unknown"),
        confidence=1.0 if spans else 0.0,
        trace=EngineTrace(
            step_id=step.step_id,
            engine=step.engine,
            capability=step.capability,
            duration_ms=0,
            counters={
                "dense_result_count": len(execution.dense_evidence),
                "sparse_result_count": len(execution.sparse_evidence),
                "fused_result_count": len(fused),
                "validated_result_count": len(spans),
            },
        ),
    )
    return RetrievalBridgeResult(result, len(fused))


def _validate_projection_evidence(
    item: Evidence, source: TrustedSource | None, scope: GenerationScope
) -> None:
    if source is None:
        raise RetrievalBridgeIntegrityError("retrieval evidence has no trusted chunk binding")
    logical_document_id = item.metadata.get("logical_document_id")
    if (
        item.workspace_id != scope.workspace_id
        or item.metadata.get("knowledge_generation_id") != scope.generation_id
        or item.document_id != source.document_id
        or item.document_version_id != source.document_version_id
        or logical_document_id != source.logical_document_id
        or item.chunk_id != source.chunk_id
        or item.content != source.content
        or item.metadata.get("content_hash")
        != hashlib.sha256(source.content.encode("utf-8")).hexdigest()
    ):
        raise RetrievalBridgeIntegrityError(
            "retrieval evidence does not match trusted source identity"
        )
