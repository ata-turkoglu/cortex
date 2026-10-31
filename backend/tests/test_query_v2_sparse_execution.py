from __future__ import annotations

import pytest

from app.query.execution import V2DenseAdapter, V2PlanExecutor, V2SparseAdapter
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
from app.retrieval.sparse import GenerationBM25Store, SparseDocument, WorkspaceBM25Index


class Resolver:
    def __init__(self, generation_id: str = "generation-42") -> None:
        self.generation_id = generation_id
        self.calls = 0

    def resolve(self, workspace_id: str) -> GenerationScope:
        self.calls += 1
        return GenerationScope(workspace_id, self.generation_id, "embedding-hash")


class DenseStore:
    def search_generation(self, query_vector, limit, scope):
        return []


def _plan(workspace_id: str = "workspace-a") -> PhysicalExecutionPlan:
    retrieval = ExecutionStep(
        step_id="execute.retrieve",
        engine="retrieval",
        capability="retrieval.hybrid_search",
        output_type="evidence_set",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id=workspace_id, generation_id="generation-42"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=("retrieve",), selection_reason="test sparse retrieval"),
    )
    reconcile = ExecutionStep(
        step_id="execute.reconcile",
        engine="result_evidence",
        capability="evidence.reconcile_and_validate",
        dependencies=(retrieval.step_id,),
        input_types=("evidence_set",),
        output_type="evidence_package",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id=workspace_id),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(logical_node_ids=("retrieve",), selection_reason="test reconciliation"),
    )
    return PhysicalExecutionPlan(
        workspace_id=workspace_id,
        state="ready",
        graph=ExecutionPlanGraph(steps=(retrieval, reconcile), root_step_ids=(reconcile.step_id,)),
    )


def _write(
    root,
    workspace: str,
    generation: str,
    content: str,
    *,
    artifact_generation=None,
    evidence_generation=None,
):
    evidence = Evidence(
        workspace,
        "knowledge_candidate",
        content,
        0.0,
        chunk_id=f"{workspace}-{generation}",
        metadata={"knowledge_generation_id": evidence_generation or generation},
    )
    WorkspaceBM25Index(
        workspace,
        [SparseDocument(evidence.chunk_id or "", content, evidence)],
        root / "workspaces" / workspace / "knowledge-candidates" / generation / "bm25",
        generation_id=artifact_generation or generation,
    ).save()


def _execute(root, resolver, *, workspace="workspace-a", query="needle"):
    return V2PlanExecutor(
        resolver, V2DenseAdapter(DenseStore()), V2SparseAdapter(GenerationBM25Store(root))
    ).execute(_plan(workspace), [1.0], dense_limit=2, query_text=query, sparse_limit=2)


def test_sparse_execution_reads_only_resolved_generation_artifact(tmp_path):
    _write(tmp_path, "workspace-a", "generation-41", "needle needle old")
    _write(tmp_path, "workspace-a", "generation-42", "needle new")
    resolver = Resolver()

    result = _execute(tmp_path, resolver)

    assert resolver.calls == 1
    assert [item.content for item in result.sparse_evidence] == ["needle new"]
    assert result.trace.sparse_engine == "sparse/bm25"
    assert result.trace.sparse_result_count == 1
    assert result.trace.sparse_artifact_identity == "workspace-a:generation-42:bm25"


def test_sparse_execution_isolates_workspace_with_same_generation_id(tmp_path):
    _write(tmp_path, "workspace-a", "generation-42", "needle local")
    _write(tmp_path, "workspace-b", "generation-42", "needle foreign")

    result = _execute(tmp_path, Resolver())

    assert [item.content for item in result.sparse_evidence] == ["needle local"]


def test_missing_generation_bm25_fails_closed_without_legacy_lookup(tmp_path):
    class NoLegacyStore(GenerationBM25Store):
        def search(self, *args, **kwargs):
            raise AssertionError("legacy BM25 must not be called")

    _write(tmp_path, "workspace-a", "legacy", "needle legacy")
    executor = V2PlanExecutor(
        Resolver(), V2DenseAdapter(DenseStore()), V2SparseAdapter(NoLegacyStore(tmp_path))
    )

    with pytest.raises(RuntimeError, match="GENERATION_BM25_NOT_READY"):
        executor.execute(_plan(), [1.0], dense_limit=1, query_text="needle")


def test_empty_generation_result_does_not_use_legacy_bm25(tmp_path):
    class NoLegacyStore(GenerationBM25Store):
        legacy_calls = 0

        def search_generation(self, scope, query, limit):
            # Deterministically model an existing generation artifact with no lexical match.
            WorkspaceBM25Index.load_generation(
                scope,
                self.data_root / "workspaces" / scope.workspace_id / "knowledge-candidates",
            )
            return []

        def search(self, *args, **kwargs):
            self.legacy_calls += 1
            raise AssertionError("legacy BM25 must not be called")

    _write(tmp_path, "workspace-a", "generation-42", "different vocabulary")
    _write(tmp_path, "workspace-a", "legacy", "needle legacy")
    store = NoLegacyStore(tmp_path)
    result = V2PlanExecutor(
        Resolver(), V2DenseAdapter(DenseStore()), V2SparseAdapter(store)
    ).execute(_plan(), [1.0], dense_limit=1, query_text="needle")

    assert result.sparse_evidence == ()
    assert store.legacy_calls == 0


def test_wrong_generation_artifact_is_rejected(tmp_path):
    _write(tmp_path, "workspace-a", "generation-42", "needle", artifact_generation="generation-41")

    with pytest.raises(RuntimeError, match="GENERATION_MISMATCH"):
        _execute(tmp_path, Resolver())


def test_sparse_execution_keeps_scope_snapshot_when_pointer_changes(tmp_path):
    _write(tmp_path, "workspace-a", "generation-42", "needle old")
    _write(tmp_path, "workspace-a", "generation-43", "needle new")

    class PointerStore(GenerationBM25Store):
        def __init__(self, data_root, resolver):
            super().__init__(data_root)
            self.resolver = resolver
            self.scopes = []

        def search_generation(self, scope, query, limit):
            self.scopes.append(scope)
            self.resolver.generation_id = "generation-43"
            return super().search_generation(scope, query, limit)

    resolver = Resolver()
    store = PointerStore(tmp_path, resolver)
    executor = V2PlanExecutor(resolver, V2DenseAdapter(DenseStore()), V2SparseAdapter(store))

    first = executor.execute(_plan(), [1.0], dense_limit=1, query_text="needle")
    second = executor.execute(_plan(), [1.0], dense_limit=1, query_text="needle")

    assert [item.content for item in first.sparse_evidence] == ["needle old"]
    assert store.scopes[0].generation_id == "generation-42"
    assert [item.content for item in second.sparse_evidence] == ["needle new"]
