import json

import pytest
from pydantic import ValidationError

from app.query.orchestration import (
    CompletenessReport,
    EngineFailure,
    EngineResult,
    EngineTrace,
    EvidenceReconciliationError,
    ExactEvidenceSpan,
    ExpectedResultStep,
    GraphRAGFinding,
    GroundedItem,
    ProvenanceLink,
    ReasoningPackage,
    ReconciliationContract,
    ResultAmbiguity,
    TrustedSource,
    reconcile_engine_results,
)

WORKSPACE = "workspace-1"
GENERATION = "generation-7"
CONTENT = "Alpha owns parcel 42."


def _source() -> TrustedSource:
    return TrustedSource(
        workspace_id=WORKSPACE,
        document_id="document-1",
        document_version_id="version-1",
        logical_document_id="logical-1",
        chunk_id="chunk-1",
        content=CONTENT,
        generation_id=GENERATION,
        citation_label="Register A",
    )


def _evidence(
    evidence_id: str = "evidence-1",
    *,
    text: str = "owns parcel 42",
    generation: str = GENERATION,
    relevance: float = 0.8,
) -> ExactEvidenceSpan:
    return ExactEvidenceSpan(
        evidence_id=evidence_id,
        workspace_id=WORKSPACE,
        document_id="document-1",
        document_version_id="version-1",
        logical_document_id="logical-1",
        chunk_id="chunk-1",
        start_offset=6,
        end_offset=20,
        source_text=text,
        generation_id=generation,
        relevance_score=relevance,
        quality_score=0.9,
    )


def _completeness(
    coverage: str = "grounded",
    state: str = "unknown",
    *,
    projections: tuple[str, ...] = (),
) -> CompletenessReport:
    if state == "complete":
        return CompletenessReport(
            coverage="exhaustive",
            state="complete",
            boundary="all active workspace records",
            generation_id=GENERATION,
            candidate_count=1,
            processed_count=1,
            ready_projections=projections,
        )
    return CompletenessReport(coverage=coverage, state=state)


def _result(
    *,
    result_id: str = "result-1",
    step_id: str = "step.retrieve",
    engine: str = "retrieval",
    capability: str = "retrieval.hybrid_search",
    evidence: tuple[ExactEvidenceSpan, ...] | None = None,
    rows: tuple[GroundedItem, ...] | None = None,
    findings: tuple[GraphRAGFinding, ...] = (),
    completeness: CompletenessReport | None = None,
    state: str = "success",
    failures: tuple[EngineFailure, ...] = (),
    ambiguities: tuple[ResultAmbiguity, ...] = (),
    generation: str | None = GENERATION,
) -> EngineResult:
    evidence = (_evidence(),) if evidence is None else evidence
    rows = (
        GroundedItem(
            item_id="row-1",
            values={"owner": "Alpha", "parcel": 42},
            evidence_ids=(evidence[0].evidence_id,),
        ),
    ) if rows is None and evidence else (() if rows is None else rows)
    return EngineResult(
        result_id=result_id,
        workspace_id=WORKSPACE,
        generation_id=generation,
        step_id=step_id,
        engine=engine,
        capability=capability,
        state=state,
        structured_rows=rows,
        text_evidence=evidence,
        graphrag_findings=findings,
        provenance=tuple(
            ProvenanceLink(result_id=item.item_id, evidence_ids=item.evidence_ids)
            for item in rows + findings
        ),
        completeness=completeness or _completeness(),
        confidence=0.85,
        ambiguities=ambiguities,
        failures=failures,
        trace=EngineTrace(
            step_id=step_id,
            engine=engine,
            capability=capability,
            duration_ms=12,
            counters={"returned": len(rows) + len(findings)},
        ),
    )


def _contract(
    *steps: str,
    coverage: str = "grounded",
    projections: tuple[str, ...] = (),
) -> ReconciliationContract:
    return ReconciliationContract(
        workspace_id=WORKSPACE,
        coverage=coverage,
        generation_id=GENERATION if coverage == "exhaustive" else None,
        boundary="all active workspace records" if coverage == "exhaustive" else None,
        expected_steps=tuple(
            ExpectedResultStep(
                step_id=step_id,
                engine="knowledge_graph" if step_id == "step.graph" else "retrieval",
                capability=(
                    "graph.traverse"
                    if step_id == "step.graph"
                    else "retrieval.hybrid_search"
                ),
            )
            for step_id in (steps or ("step.retrieve",))
        ),
        mandatory_projections=projections,
        partial_results_allowed=coverage != "exhaustive",
    )


def test_engine_result_is_versioned_complete_and_cannot_author_an_answer():
    properties = EngineResult.model_json_schema()["properties"]
    for field in (
        "structured_rows",
        "entities",
        "graph_paths",
        "aggregates",
        "text_evidence",
        "graphrag_findings",
        "claims",
        "provenance",
        "completeness",
        "confidence",
        "ambiguities",
        "conflicts",
        "failures",
        "trace",
    ):
        assert field in properties
    assert "final_answer" not in properties
    assert "answer" not in properties
    package_properties = ReasoningPackage.model_json_schema()["properties"]
    assert "final_answer" not in package_properties
    assert "answer" not in package_properties
    payload = _result().model_dump()
    payload["final_answer"] = "Engine-authored prose must not pass."
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EngineResult.model_validate(payload)


def test_exact_span_is_materialized_to_a_traceable_ranked_citation():
    package = reconcile_engine_results(_contract(), (_result(),), (_source(),))

    assert package.state == "grounded"
    assert len(package.citations) == 1
    citation = package.citations[0]
    assert citation.source_text == CONTENT[citation.start_offset : citation.end_offset]
    assert (citation.document_version_id, citation.logical_document_id, citation.chunk_id) == (
        "version-1",
        "logical-1",
        "chunk-1",
    )
    assert citation.supporting_step_ids == ("step.retrieve",)
    assert package.provenance[0].evidence_ids == (citation.evidence_id,)


def test_workspace_boundaries_fail_closed_before_reconciliation():
    foreign = _result().model_copy(update={"workspace_id": "workspace-2"})

    with pytest.raises(EvidenceReconciliationError, match="workspace"):
        reconcile_engine_results(_contract(), (foreign,), (_source(),))


def test_result_capability_must_match_the_physical_plan():
    wrong_capability = _result().model_copy(update={"capability": "retrieval.semantic_search"})

    with pytest.raises(EvidenceReconciliationError, match="physical plan"):
        reconcile_engine_results(_contract(), (wrong_capability,), (_source(),))


def test_invalid_exact_span_is_excluded_and_visible_as_unsupported():
    result = _result(evidence=(_evidence(text="owns parcel 43"),))

    package = reconcile_engine_results(_contract(), (result,), (_source(),))

    assert package.state == "unsupported"
    assert package.citations == ()
    assert package.structured_rows == ()
    assert "failed exact-span validation" in package.issues[0]


def test_duplicate_compatible_items_and_spans_merge_across_engines():
    first = _result()
    second_evidence = _evidence("evidence-2", relevance=0.95)
    second = _result(
        result_id="result-2",
        step_id="step.graph",
        engine="knowledge_graph",
        capability="graph.traverse",
        evidence=(second_evidence,),
        rows=(
            GroundedItem(
                item_id="row-1",
                values={"owner": "Alpha", "parcel": 42},
                evidence_ids=("evidence-2",),
            ),
        ),
    )

    package = reconcile_engine_results(
        _contract("step.retrieve", "step.graph"), (first, second), (_source(),)
    )

    assert len(package.structured_rows) == 1
    assert package.structured_rows[0].evidence_ids == ("evidence-1",)
    assert package.citations[0].supporting_step_ids == ("step.graph", "step.retrieve")
    assert package.citations[0].score > 0.9


def test_different_values_for_one_identity_are_preserved_as_conflict():
    first = _result()
    second = _result(
        result_id="result-2",
        step_id="step.graph",
        engine="knowledge_graph",
        capability="graph.traverse",
        rows=(
            GroundedItem(
                item_id="row-1",
                values={"owner": "Alpha", "parcel": 43},
                evidence_ids=("evidence-1",),
            ),
        ),
    )

    package = reconcile_engine_results(
        _contract("step.retrieve", "step.graph"), (first, second), (_source(),)
    )

    assert len(package.structured_rows) == 2
    assert len(package.conflicts) == 1
    assert package.conflicts[0].left_result_id != package.conflicts[0].right_result_id


def test_partial_failure_remains_visible_and_cannot_be_promoted():
    package = reconcile_engine_results(
        _contract("step.retrieve", "step.graph"), (_result(),), (_source(),)
    )

    assert package.state == "partial"
    assert package.failures[0].step_id == "step.graph"
    assert "returned no result" in package.failures[0].reason


def test_exhaustive_same_generation_and_projections_can_be_corpus_complete():
    complete = _result(
        completeness=_completeness(state="complete", projections=("canonical_entities",))
    )

    package = reconcile_engine_results(
        _contract(
            "step.retrieve", coverage="exhaustive", projections=("canonical_entities",)
        ),
        (complete,),
        (_source(),),
    )

    assert package.state == "corpus_complete"
    assert package.completeness.state == "complete"
    assert package.completeness.candidate_count == package.completeness.processed_count


def test_generation_mismatch_and_missing_projection_fail_closed():
    complete = _result(
        completeness=_completeness(state="complete", projections=("canonical_entities",))
    )
    failure = EngineFailure(
        step_id="step.graph",
        engine="knowledge_graph",
        capability="graph.traverse",
        reason="generation changed before traversal",
    )
    mismatched = _result(
        result_id="result-2",
        step_id="step.graph",
        engine="knowledge_graph",
        capability="graph.traverse",
        evidence=(),
        rows=(),
        completeness=_completeness(state="partial"),
        state="failed",
        failures=(failure,),
        generation="generation-8",
    )

    package = reconcile_engine_results(
        _contract(
            "step.retrieve", "step.graph",
            coverage="exhaustive",
            projections=("canonical_entities", "graphrag_communities"),
        ),
        (complete, mismatched),
        (_source(),),
    )

    assert package.state == "unsupported"
    assert package.completeness.state == "partial"
    assert package.completeness.missing_projections == ("graphrag_communities",)
    assert any("generation" in issue for issue in package.issues)


def test_conflicting_reuse_of_evidence_id_invalidates_every_occurrence():
    first = _result()
    conflicting = _result(
        result_id="result-2",
        step_id="step.graph",
        engine="knowledge_graph",
        capability="graph.traverse",
        evidence=(
            _evidence().model_copy(
                update={
                    "start_offset": 0,
                    "end_offset": 5,
                    "source_text": "Alpha",
                }
            ),
        ),
    )

    package = reconcile_engine_results(
        _contract("step.retrieve", "step.graph"), (first, conflicting), (_source(),)
    )

    assert package.state == "unsupported"
    assert package.citations == ()
    assert "identifies conflicting spans" in package.issues[0]


def test_graphrag_native_prose_requires_declared_exact_evidence():
    finding = GraphRAGFinding(
        item_id="finding-1",
        values={"community": "c1"},
        evidence_ids=("missing-evidence",),
        mode="global",
        text="A native GraphRAG narrative.",
    )

    with pytest.raises(ValidationError, match="undeclared evidence"):
        _result(evidence=(), rows=(), findings=(finding,), engine="graphrag")


def test_ambiguity_has_priority_over_available_grounded_material():
    ambiguity = ResultAmbiguity(
        ambiguity_id="ambiguous-owner",
        reason="Two people share the alias",
        candidate_ids=("person-1", "person-2"),
    )
    result = _result(state="ambiguous", ambiguities=(ambiguity,))

    package = reconcile_engine_results(_contract(), (result,), (_source(),))

    assert package.state == "ambiguous"
    assert package.ambiguities == (ambiguity,)


def test_engine_result_json_round_trip_retains_typed_contract():
    result = _result()

    restored = EngineResult.model_validate_json(json.dumps(result.model_dump(mode="json")))

    assert restored == result
