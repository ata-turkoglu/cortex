import hashlib

import pytest

from app.query.execution import V2ExecutionResult, V2ExecutionTrace
from app.query.orchestration import TrustedSource
from app.query.orchestration.retrieval_bridge import (
    RetrievalBridgeIntegrityError,
    bridge_retrieval,
)
from app.query.planning import (
    ExecutionPlanGraph,
    ExecutionStep,
    FailurePolicy,
    PhysicalExecutionPlan,
    PlanTrace,
    ReadinessRequirement,
)
from app.query.scope import GenerationScope
from app.retrieval.schemas import Evidence


def _plan():
    step = ExecutionStep(
        step_id="execute.retrieve",
        engine="retrieval",
        capability="retrieval.hybrid_search",
        output_type="evidence_set",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace", generation_id="generation"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=("retrieve",), selection_reason="test"),
    )
    reconcile = ExecutionStep(
        step_id="execute.reconcile",
        engine="result_evidence",
        capability="evidence.reconcile_and_validate",
        dependencies=(step.step_id,),
        input_types=("evidence_set",),
        output_type="evidence_package",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=("retrieve",), selection_reason="test"),
    )
    return PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(steps=(step, reconcile), root_step_ids=(reconcile.step_id,)),
    )


def _source():
    return TrustedSource(
        workspace_id="workspace",
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk",
        content="trusted evidence",
        citation_label="Source",
    )


def _evidence(score=0.7, content="trusted evidence"):
    return Evidence(
        "workspace",
        "qdrant:chunks",
        content,
        score,
        "document",
        "version",
        "chunk",
        "Source",
        {
            "knowledge_generation_id": "generation",
            "logical_document_id": "logical",
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        },
    )


def test_bridge_fuses_and_materializes_whole_authoritative_chunk():
    execution = V2ExecutionResult(
        V2ExecutionTrace(
            "workspace", "generation", "embedding", "retrieval.hybrid_search", 1, "sparse/bm25", 1
        ),
        (_evidence(),),
        (_evidence(0.6),),
    )
    result = bridge_retrieval(
        _plan(),
        execution,
        GenerationScope("workspace", "generation", "embedding"),
        (_source(),),
        limit=10,
    )
    assert result.fused_count == 1
    assert result.engine_result.text_evidence[0].source_text == "trusted evidence"
    assert result.engine_result.structured_rows[0].values["fusion_rank"] == 1


def test_bridge_rejects_tampered_projection_content():
    execution = V2ExecutionResult(
        V2ExecutionTrace("workspace", "generation", "embedding", "retrieval.hybrid_search", 1),
        (_evidence(content="tampered"),),
    )
    with pytest.raises(RetrievalBridgeIntegrityError, match="trusted source identity"):
        bridge_retrieval(
            _plan(),
            execution,
            GenerationScope("workspace", "generation", "embedding"),
            (_source(),),
            limit=10,
        )
