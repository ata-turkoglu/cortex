import hashlib

import pytest

from app.graphrag.adapter import (
    GraphRAGFindingCandidate,
    GraphRAGSourceReference,
    GraphRoute,
)
from app.query.answer import AnswerEngine
from app.query.execution import ProductionEngineRegistry, V2DenseAdapter, V2PlanExecutor
from app.query.ir.schemas import CustomCapabilityNode
from app.query.orchestration import (
    CompletenessReport,
    EngineResult,
    EngineTrace,
    ExpectedResultStep,
    GroundedItem,
    ReconciliationContract,
    TrustedSource,
    reconcile_engine_results,
)
from app.query.orchestration.graphrag_bridge import GraphRAGBridgeIntegrityError
from app.query.planning import (
    ExecutionPlanGraph,
    ExecutionStep,
    FailurePolicy,
    PhysicalExecutionPlan,
    PlanTrace,
    ReadinessRequirement,
)
from app.query.production_engines import GraphRAGProductionEngine
from app.query.scope import GenerationScope


class FixedScope:
    scope = GenerationScope("workspace", "generation", "embedding")

    def resolve(self, workspace_id):
        assert workspace_id == self.scope.workspace_id
        return self.scope


class EmptyDense:
    def search_generation(self, query_vector, limit, scope):
        return []


class FixtureGraphRAG:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []

    def query_findings(self, mode, query, generation_id, limit=10):
        self.calls.append((mode, query, generation_id))
        return (self.candidate,)


def _source():
    return TrustedSource(
        workspace_id="workspace",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk",
        content="Source evidence for trusted GraphRAG finding.",
        generation_id="generation",
        citation_label="Trusted source",
    )


def _candidate(mode=GraphRoute.LOCAL, **updates):
    source = _source()
    reference = GraphRAGSourceReference(
        workspace_id=source.workspace_id,
        generation_id=source.generation_id,
        document_id=source.document_id,
        document_version_id=source.document_version_id,
        logical_document_id=source.logical_document_id,
        chunk_id=source.chunk_id,
        content_hash=hashlib.sha256(source.content.encode("utf-8")).hexdigest(),
    )
    return GraphRAGFindingCandidate(
        mode=mode,
        artifact_id="artifact-1",
        text="NATIVE GRAPH RAG ANSWER MUST NOT BE RETURNED DIRECTLY",
        source=reference,
        score=0.8,
    ).__class__(
        mode=mode,
        artifact_id="artifact-1",
        text="NATIVE GRAPH RAG ANSWER MUST NOT BE RETURNED DIRECTLY",
        source=updates.get("source", reference),
        score=0.8,
    )


def _step(mode, node_id="graphrag"):
    return ExecutionStep(
        step_id="execute.graphrag",
        engine="graphrag",
        capability=f"graphrag.{mode.value}",
        output_type="extension",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace", generation_id="generation"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=(node_id,), selection_reason="test"),
    )


@pytest.mark.parametrize("mode", (GraphRoute.LOCAL, GraphRoute.GLOBAL, GraphRoute.DRIFT))
def test_graphrag_modes_execute_through_v2_registry_with_exact_provenance(mode):
    node = CustomCapabilityNode(node_id="graphrag", capability=f"graphrag.{mode.value}")
    step = _step(mode)
    fixture = FixtureGraphRAG(_candidate(mode))
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(steps=(step,), root_step_ids=(step.step_id,)),
    )
    execution = V2PlanExecutor(
        FixedScope(),
        V2DenseAdapter(EmptyDense()),
        registry=ProductionEngineRegistry(
            {"graphrag": GraphRAGProductionEngine(lambda _: fixture)}
        ),
    ).execute_plan(
        plan,
        (node,),
        query_vector=None,
        query_text="trusted graph query",
        trusted_sources=(_source(),),
    )

    result = execution.results[0]
    assert fixture.calls == [(mode, "trusted graph query", "generation")]
    assert result.state == "success"
    assert result.graphrag_findings[0].mode == mode.value
    assert result.text_evidence[0].chunk_id == "chunk"
    assert result.generation_id == "generation"


@pytest.mark.parametrize(
    "reference",
    (
        GraphRAGSourceReference(
            "other", "generation", "document", "version", "logical", "chunk", "x"
        ),
        GraphRAGSourceReference(
            "workspace", "other", "document", "version", "logical", "chunk", "x"
        ),
        GraphRAGSourceReference(
            "workspace", "generation", "document", "version", "logical", "unknown", "x"
        ),
        GraphRAGSourceReference(
            "workspace", "generation", "document", "version", "logical", "chunk", "tampered"
        ),
    ),
)
def test_graphrag_bridge_rejects_cross_scope_unknown_and_tampered_references(reference):
    mode = GraphRoute.LOCAL
    node = CustomCapabilityNode(node_id="graphrag", capability="graphrag.local")
    step = _step(mode)
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(steps=(step,), root_step_ids=(step.step_id,)),
    )
    engine = GraphRAGProductionEngine(lambda _: FixtureGraphRAG(_candidate(source=reference)))
    with pytest.raises(GraphRAGBridgeIntegrityError):
        V2PlanExecutor(
            FixedScope(),
            V2DenseAdapter(EmptyDense()),
            registry=ProductionEngineRegistry({"graphrag": engine}),
        ).execute_plan(
            plan, (node,), query_vector=None, query_text="query", trusted_sources=(_source(),)
        )


def test_graphrag_reconciles_with_structured_result_and_answer_engine_renders_final_prose():
    mode = GraphRoute.LOCAL
    node = CustomCapabilityNode(node_id="graphrag", capability="graphrag.local")
    step = _step(mode)
    fixture = FixtureGraphRAG(_candidate(mode))
    plan = PhysicalExecutionPlan(
        workspace_id="workspace",
        state="ready",
        graph=ExecutionPlanGraph(steps=(step,), root_step_ids=(step.step_id,)),
    )
    graphrag = (
        V2PlanExecutor(
            FixedScope(),
            V2DenseAdapter(EmptyDense()),
            registry=ProductionEngineRegistry(
                {"graphrag": GraphRAGProductionEngine(lambda _: fixture)}
            ),
        )
        .execute_plan(
            plan, (node,), query_vector=None, query_text="query", trusted_sources=(_source(),)
        )
        .results[0]
    )
    structured = EngineResult(
        result_id="structured-result",
        workspace_id="workspace",
        generation_id="generation",
        step_id="execute.structured",
        engine="structured",
        capability="structured.enumerate",
        state="success",
        structured_rows=(
            GroundedItem(
                item_id="row",
                values={"name": "Merter"},
                evidence_ids=(graphrag.text_evidence[0].evidence_id,),
            ),
        ),
        text_evidence=graphrag.text_evidence,
        completeness=CompletenessReport(coverage="grounded", state="unknown"),
        confidence=1.0,
        trace=EngineTrace(
            step_id="execute.structured",
            engine="structured",
            capability="structured.enumerate",
            duration_ms=0,
        ),
    )
    package = reconcile_engine_results(
        ReconciliationContract(
            workspace_id="workspace",
            generation_id="generation",
            coverage="grounded",
            expected_steps=(
                ExpectedResultStep(
                    step_id=structured.step_id,
                    engine="structured",
                    capability="structured.enumerate",
                ),
                ExpectedResultStep(
                    step_id=graphrag.step_id, engine="graphrag", capability="graphrag.local"
                ),
            ),
        ),
        (structured, graphrag),
        (_source(),),
    )
    answer = AnswerEngine().render(package)
    assert package.graphrag_findings and package.structured_rows
    assert answer.content != graphrag.graphrag_findings[0].text
    assert answer.metadata["answer_engine"] == "query_v2"
