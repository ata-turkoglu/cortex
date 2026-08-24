"""Fail-closed normalization of GraphRAG artifacts into V2 Result & Evidence."""

from __future__ import annotations

import hashlib
from time import perf_counter

from ...graphrag.adapter import GraphRAGFindingCandidate
from ..execution import EngineExecutionContext, EngineExecutionOutput
from .schemas import (
    CompletenessReport,
    EngineResult,
    EngineTrace,
    ExactEvidenceSpan,
    GraphRAGFinding,
    ProvenanceLink,
    TrustedSource,
)


class GraphRAGBridgeIntegrityError(ValueError):
    """A GraphRAG artifact cannot be bound to an immutable trusted chunk."""


def bridge_graphrag(
    context: EngineExecutionContext,
    candidates: tuple[GraphRAGFindingCandidate, ...],
) -> EngineExecutionOutput:
    """Emit one normal EngineResult, admitting only exact trusted references."""
    started = perf_counter()
    scope = context.scope
    sources = tuple(context.trusted_sources)
    if any(
        not isinstance(source, TrustedSource)
        or source.workspace_id != scope.workspace_id
        or source.generation_id != scope.generation_id
        for source in sources
    ):
        raise GraphRAGBridgeIntegrityError("trusted sources cross immutable generation scope")
    source_by_chunk = {source.chunk_id: source for source in sources}
    if len(source_by_chunk) != len(sources):
        raise GraphRAGBridgeIntegrityError("trusted source binding is ambiguous")

    spans: list[ExactEvidenceSpan] = []
    findings: list[GraphRAGFinding] = []
    links: list[ProvenanceLink] = []
    for rank, candidate in enumerate(candidates, start=1):
        source = source_by_chunk.get(candidate.source.chunk_id)
        if source is None or (
            candidate.source.workspace_id != scope.workspace_id
            or candidate.source.generation_id != scope.generation_id
            or candidate.source.document_id != source.document_id
            or candidate.source.document_version_id != source.document_version_id
            or candidate.source.logical_document_id != source.logical_document_id
            or candidate.source.content_hash
            != hashlib.sha256(source.content.encode("utf-8")).hexdigest()
        ):
            raise GraphRAGBridgeIntegrityError(
                "GraphRAG source reference does not match trusted source identity"
            )
        evidence_id = f"graphrag-{scope.generation_id[:12]}-{rank}"
        finding_id = f"graphrag-finding-{candidate.artifact_id}"
        spans.append(
            ExactEvidenceSpan(
                evidence_id=evidence_id,
                workspace_id=source.workspace_id,
                document_id=source.document_id,
                document_version_id=source.document_version_id,
                logical_document_id=source.logical_document_id,
                chunk_id=source.chunk_id,
                start_offset=0,
                end_offset=len(source.content),
                source_text=source.content,
                generation_id=source.generation_id,
                relevance_score=max(0.0, min(1.0, candidate.score)),
                quality_score=1.0,
            )
        )
        findings.append(
            GraphRAGFinding(
                item_id=finding_id,
                mode=candidate.mode.value,
                text=candidate.text,
                values={"artifact_id": candidate.artifact_id, "mode": candidate.mode.value},
                evidence_ids=(evidence_id,),
            )
        )
        links.append(ProvenanceLink(result_id=finding_id, evidence_ids=(evidence_id,)))
    result = EngineResult(
        result_id=f"graphrag-result-{context.step.step_id}",
        workspace_id=scope.workspace_id,
        generation_id=scope.generation_id,
        step_id=context.step.step_id,
        engine=context.step.engine,
        capability=context.step.capability,
        state="success" if findings else "unsupported",
        text_evidence=tuple(spans),
        graphrag_findings=tuple(findings),
        provenance=tuple(links),
        completeness=CompletenessReport(
            coverage="grounded", state="unknown", generation_id=scope.generation_id
        ),
        confidence=1.0 if findings else 0.0,
        trace=EngineTrace(
            step_id=context.step.step_id,
            engine=context.step.engine,
            capability=context.step.capability,
            duration_ms=int((perf_counter() - started) * 1_000),
            counters={
                "artifact_finding_count": len(candidates),
                "validated_finding_count": len(findings),
            },
        ),
    )
    return EngineExecutionOutput(None, result)
