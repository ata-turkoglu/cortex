"""Fail-closed normalization and reconciliation for detached engine results."""

from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel

from .schemas import (
    CompletenessReport,
    EngineFailure,
    EngineResult,
    ExactEvidenceSpan,
    GroundedItem,
    MaterializedCitation,
    ProvenanceLink,
    ReasoningPackage,
    ReconciliationContract,
    ResultAmbiguity,
    ResultConflict,
    TrustedSource,
)


class EvidenceReconciliationError(ValueError):
    pass


ItemT = TypeVar("ItemT", bound=GroundedItem)


def reconcile_engine_results(
    contract: ReconciliationContract,
    results: tuple[EngineResult, ...],
    trusted_sources: tuple[TrustedSource, ...],
) -> ReasoningPackage:
    """Reconcile detached values only; callers own any surrounding short transaction."""
    _validate_boundaries(contract, results, trusted_sources)
    issues: list[str] = []
    failures = [failure for result in results for failure in result.failures]
    by_step = {result.step_id: result for result in results}
    for expected in contract.expected_steps:
        if expected.required and expected.step_id not in by_step:
            failures.append(
                EngineFailure(
                    step_id=expected.step_id,
                    engine="orchestration",
                    capability="evidence.missing_step",
                    reason="required execution step returned no result",
                )
            )

    valid_evidence, evidence_aliases, evidence_steps, evidence_issues = _validate_evidence(
        contract, results, trusted_sources
    )
    issues.extend(evidence_issues)
    valid_ids = set(evidence_aliases.values())

    rows, row_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.structured_rows),
        evidence_aliases,
        valid_ids,
        "structured_row",
    )
    entities, entity_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.entities),
        evidence_aliases,
        valid_ids,
        "entity",
    )
    paths, path_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.graph_paths),
        evidence_aliases,
        valid_ids,
        "graph_path",
    )
    aggregates, aggregate_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.aggregates),
        evidence_aliases,
        valid_ids,
        "aggregate",
    )
    findings, finding_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.graphrag_findings),
        evidence_aliases,
        valid_ids,
        "graphrag_finding",
    )
    claims, claim_conflicts = _reconcile_items(
        tuple(item for result in results for item in result.claims),
        evidence_aliases,
        valid_ids,
        "claim",
    )
    auto_conflicts = (
        row_conflicts
        + entity_conflicts
        + path_conflicts
        + aggregate_conflicts
        + finding_conflicts
        + claim_conflicts
    )
    declared_conflicts = tuple(conflict for result in results for conflict in result.conflicts)
    conflicts = _dedupe_models(declared_conflicts + auto_conflicts)
    ambiguities = _dedupe_models(
        tuple(ambiguity for result in results for ambiguity in result.ambiguities)
    )
    provenance = _valid_provenance(results, evidence_aliases, valid_ids)
    citations = _materialize_citations(valid_evidence, trusted_sources, evidence_steps)
    source_count = len(
        {(item.document_version_id, item.chunk_id) for item in valid_evidence}
    )
    if source_count < contract.minimum_sources:
        issues.append(
            f"validated source count {source_count} is below required {contract.minimum_sources}"
        )

    completeness = _reconcile_completeness(contract, results, failures, issues)
    useful_count = sum(
        len(items) for items in (rows, entities, paths, aggregates, findings, claims)
    )
    state = _answer_state(
        contract,
        results,
        completeness,
        useful_count,
        source_count,
        ambiguities,
        failures,
        issues,
    )
    successful_confidence = [
        result.confidence for result in results if result.state in {"success", "partial"}
    ]
    confidence = (
        sum(successful_confidence) / len(successful_confidence) if successful_confidence else 0.0
    )
    return ReasoningPackage(
        workspace_id=contract.workspace_id,
        generation_id=contract.generation_id,
        state=state,
        structured_rows=rows,
        entities=entities,
        graph_paths=paths,
        aggregates=aggregates,
        graphrag_findings=findings,
        claims=claims,
        citations=citations,
        provenance=provenance,
        completeness=completeness,
        confidence=confidence,
        ambiguities=ambiguities,
        conflicts=conflicts,
        failures=tuple(failures),
        traces=tuple(result.trace for result in results),
        issues=tuple(dict.fromkeys(issues)),
    )


def _validate_boundaries(
    contract: ReconciliationContract,
    results: tuple[EngineResult, ...],
    sources: tuple[TrustedSource, ...],
) -> None:
    if any(result.workspace_id != contract.workspace_id for result in results):
        raise EvidenceReconciliationError("engine result crosses the reconciliation workspace")
    if any(source.workspace_id != contract.workspace_id for source in sources):
        raise EvidenceReconciliationError("trusted source crosses the reconciliation workspace")
    result_step_ids = [result.step_id for result in results]
    if len(result_step_ids) != len(set(result_step_ids)):
        raise EvidenceReconciliationError("an execution step returned more than one result")
    result_ids = [result.result_id for result in results]
    if len(result_ids) != len(set(result_ids)):
        raise EvidenceReconciliationError("engine result identifiers must be unique")
    expected = {step.step_id: step for step in contract.expected_steps}
    for result in results:
        planned = expected.get(result.step_id)
        if planned is None:
            raise EvidenceReconciliationError("engine result is not declared by the physical plan")
        if (result.engine, result.capability) != (planned.engine, planned.capability):
            raise EvidenceReconciliationError(
                "engine result capability does not match the physical plan"
            )
    source_keys = [(source.chunk_id, source.generation_id) for source in sources]
    if len(source_keys) != len(set(source_keys)):
        raise EvidenceReconciliationError("trusted sources must be unique by chunk and generation")


def _validate_evidence(
    contract: ReconciliationContract,
    results: tuple[EngineResult, ...],
    sources: tuple[TrustedSource, ...],
) -> tuple[
    tuple[ExactEvidenceSpan, ...],
    dict[str, str],
    dict[str, set[str]],
    tuple[str, ...],
]:
    source_index = {
        (
            source.document_id,
            source.document_version_id,
            source.logical_document_id,
            source.chunk_id,
            source.generation_id,
        ): source
        for source in sources
    }
    canonical: dict[tuple[object, ...], ExactEvidenceSpan] = {}
    aliases: dict[str, str] = {}
    supporting_steps: dict[str, set[str]] = defaultdict(set)
    issues: list[str] = []
    entries = tuple(
        (result, evidence) for result in results for evidence in result.text_evidence
    )
    keys_by_id: dict[str, set[tuple[object, ...]]] = defaultdict(set)
    for _, evidence in entries:
        keys_by_id[evidence.evidence_id].add(_evidence_key(evidence))
    conflicting_ids = {
        evidence_id for evidence_id, keys in keys_by_id.items() if len(keys) > 1
    }
    issues.extend(
        f"evidence id {evidence_id} identifies conflicting spans"
        for evidence_id in sorted(conflicting_ids)
    )
    for result, evidence in entries:
        if evidence.evidence_id in conflicting_ids:
            continue
        key = _evidence_key(evidence)
        if contract.generation_id and evidence.generation_id != contract.generation_id:
            issues.append(f"evidence {evidence.evidence_id} uses a different generation")
            continue
        source = source_index.get(key[:5])
        if source is None:
            issues.append(f"evidence {evidence.evidence_id} has no trusted source lineage")
            continue
        if evidence.end_offset > len(source.content) or (
            source.content[evidence.start_offset : evidence.end_offset] != evidence.source_text
        ):
            issues.append(f"evidence {evidence.evidence_id} failed exact-span validation")
            continue
        canonical_item = canonical.get(key)
        if canonical_item is None:
            canonical_item = evidence
            canonical[key] = evidence
        elif (
            evidence.relevance_score > canonical_item.relevance_score
            or evidence.quality_score > canonical_item.quality_score
        ):
            canonical_item = canonical_item.model_copy(
                update={
                    "relevance_score": max(
                        evidence.relevance_score, canonical_item.relevance_score
                    ),
                    "quality_score": max(evidence.quality_score, canonical_item.quality_score),
                }
            )
            canonical[key] = canonical_item
        aliases[evidence.evidence_id] = canonical_item.evidence_id
        supporting_steps[canonical_item.evidence_id].add(result.step_id)
    return tuple(canonical.values()), aliases, supporting_steps, tuple(issues)


def _evidence_key(evidence: ExactEvidenceSpan) -> tuple[object, ...]:
    return (
        evidence.document_id,
        evidence.document_version_id,
        evidence.logical_document_id,
        evidence.chunk_id,
        evidence.generation_id,
        evidence.start_offset,
        evidence.end_offset,
        evidence.source_text,
    )


def _reconcile_items(
    items: tuple[ItemT, ...],
    evidence_aliases: dict[str, str],
    valid_evidence_ids: set[str],
    kind: str,
) -> tuple[tuple[ItemT, ...], tuple[ResultConflict, ...]]:
    reconciled: list[ItemT] = []
    by_signature: dict[str, int] = {}
    by_id: dict[str, tuple[str, ItemT]] = {}
    conflicts: list[ResultConflict] = []
    for item in items:
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_aliases[evidence_id]
                for evidence_id in item.evidence_ids
                if evidence_aliases.get(evidence_id) in valid_evidence_ids
            )
        )
        if not evidence_ids:
            continue
        normalized = item.model_copy(update={"evidence_ids": evidence_ids})
        signature = _model_signature(normalized, exclude={"evidence_ids"})
        existing_index = by_signature.get(signature)
        if existing_index is not None:
            existing = reconciled[existing_index]
            merged_ids = tuple(dict.fromkeys(existing.evidence_ids + evidence_ids))
            reconciled[existing_index] = existing.model_copy(
                update={"evidence_ids": merged_ids}
            )
            continue
        previous = by_id.get(item.item_id)
        if previous and previous[0] != signature:
            conflict_material = f"{kind}:{item.item_id}:{previous[0]}:{signature}"
            previous_ref = sha256(previous[0].encode()).hexdigest()[:12]
            current_ref = sha256(signature.encode()).hexdigest()[:12]
            conflicts.append(
                ResultConflict(
                    conflict_id=f"conflict-{sha256(conflict_material.encode()).hexdigest()[:20]}",
                    subject=item.item_id,
                    predicate=kind,
                    left_result_id=f"{previous[1].item_id}@{previous_ref}",
                    right_result_id=f"{normalized.item_id}@{current_ref}",
                    reason=(
                        "engines returned different grounded values for the same result identity"
                    ),
                )
            )
        else:
            by_id[item.item_id] = (signature, normalized)
        by_signature[signature] = len(reconciled)
        reconciled.append(normalized)
    return tuple(reconciled), tuple(conflicts)


def _model_signature(model: BaseModel, *, exclude: set[str] | None = None) -> str:
    payload = model.model_dump(mode="json", exclude=exclude)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _dedupe_models(items: tuple[ItemT, ...]) -> tuple[ItemT, ...]:
    unique: dict[str, ItemT] = {}
    for item in items:
        unique.setdefault(_model_signature(item), item)
    return tuple(unique.values())


def _valid_provenance(
    results: tuple[EngineResult, ...],
    aliases: dict[str, str],
    valid_ids: set[str],
) -> tuple[ProvenanceLink, ...]:
    links: list[ProvenanceLink] = []
    for result in results:
        for link in result.provenance:
            evidence_ids = tuple(
                dict.fromkeys(
                    aliases[evidence_id]
                    for evidence_id in link.evidence_ids
                    if aliases.get(evidence_id) in valid_ids
                )
            )
            if evidence_ids:
                links.append(link.model_copy(update={"evidence_ids": evidence_ids}))
    return _dedupe_models(tuple(links))


def _materialize_citations(
    evidence: tuple[ExactEvidenceSpan, ...],
    sources: tuple[TrustedSource, ...],
    supporting_steps: dict[str, set[str]],
) -> tuple[MaterializedCitation, ...]:
    source_index = {(source.chunk_id, source.generation_id): source for source in sources}
    ranked = sorted(
        evidence,
        key=lambda item: (
            item.relevance_score * 0.6
            + item.quality_score * 0.3
            + min(len(supporting_steps[item.evidence_id]), 3) / 3 * 0.1,
            item.evidence_id,
        ),
        reverse=True,
    )
    citations: list[MaterializedCitation] = []
    for rank, item in enumerate(ranked, start=1):
        source = source_index[(item.chunk_id, item.generation_id)]
        score = min(
            1.0,
            item.relevance_score * 0.6
            + item.quality_score * 0.3
            + min(len(supporting_steps[item.evidence_id]), 3) / 3 * 0.1,
        )
        citations.append(
            MaterializedCitation(
                citation_id=(
                    "citation-"
                    + sha256("|".join(map(str, _evidence_key(item))).encode()).hexdigest()[:20]
                ),
                evidence_id=item.evidence_id,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                logical_document_id=item.logical_document_id,
                chunk_id=item.chunk_id,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
                source_text=item.source_text,
                label=source.citation_label,
                rank=rank,
                score=score,
                supporting_step_ids=tuple(sorted(supporting_steps[item.evidence_id])),
            )
        )
    return tuple(citations)


def _reconcile_completeness(
    contract: ReconciliationContract,
    results: tuple[EngineResult, ...],
    failures: list[EngineFailure],
    issues: list[str],
) -> CompletenessReport:
    ready_projections = {
        projection
        for result in results
        for projection in result.completeness.ready_projections
    }
    missing = set(contract.mandatory_projections) - ready_projections
    missing.update(
        projection
        for result in results
        for projection in result.completeness.missing_projections
    )
    expected = {step.step_id: step for step in contract.expected_steps}
    generation_mismatch = any(
        expected[result.step_id].generation_required
        and contract.generation_id is not None
        and result.generation_id != contract.generation_id
        for result in results
    )
    if generation_mismatch:
        issues.append("engine results contain a mixed or unexpected generation")
    candidates = [
        result.completeness.candidate_count
        for result in results
        if result.completeness.candidate_count is not None
    ]
    processed = [
        result.completeness.processed_count
        for result in results
        if result.completeness.processed_count is not None
    ]
    all_complete = bool(results) and all(
        result.state == "success" and result.completeness.state == "complete"
        for result in results
    )
    complete = (
        contract.coverage == "exhaustive"
        and all_complete
        and not failures
        and not issues
        and not missing
        and not generation_mismatch
        and {
            step.step_id for step in contract.expected_steps if step.required
        }.issubset({result.step_id for result in results})
    )
    return CompletenessReport(
        coverage=contract.coverage,
        state="complete" if complete else ("partial" if results else "unknown"),
        boundary=contract.boundary,
        generation_id=contract.generation_id,
        candidate_count=sum(candidates) if candidates else None,
        processed_count=sum(processed) if processed else None,
        ready_projections=tuple(sorted(ready_projections)),
        missing_projections=tuple(sorted(missing)),
    )


def _answer_state(
    contract: ReconciliationContract,
    results: tuple[EngineResult, ...],
    completeness: CompletenessReport,
    useful_count: int,
    citation_count: int,
    ambiguities: tuple[ResultAmbiguity, ...],
    failures: list[EngineFailure],
    issues: list[str],
) -> str:
    if ambiguities or any(result.state == "ambiguous" for result in results):
        return "ambiguous"
    has_support = useful_count > 0 and citation_count >= contract.minimum_sources
    if completeness.state == "complete" and has_support:
        return "corpus_complete"
    degraded = bool(failures or issues) or any(
        result.state in {"partial", "failed", "unsupported"} for result in results
    )
    if has_support:
        if not degraded:
            return "grounded"
        return "partial" if contract.partial_results_allowed else "unsupported"
    return "unsupported"
