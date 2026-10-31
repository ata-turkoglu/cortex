from qdrant_client import QdrantClient

from app.query.execution import V2DenseAdapter, V2PlanExecutor
from app.query.planning import (
    ExecutionPlanGraph,
    ExecutionStep,
    FailurePolicy,
    PhysicalExecutionPlan,
    PlanTrace,
    ReadinessRequirement,
)
from app.query.scope import GenerationScope
from app.retrieval.qdrant import VectorRecord, WorkspaceQdrantStore
from app.retrieval.schemas import Evidence


class ScopeResolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, workspace_id):
        self.calls += 1
        return GenerationScope(workspace_id, "generation-42", "embedding-hash")


class DenseStore:
    def __init__(self):
        self.generation_calls = []
        self.legacy_calls = 0

    def search_generation(self, query_vector, limit, scope):
        self.generation_calls.append((query_vector, limit, scope))
        return [
            Evidence(
                scope.workspace_id,
                "qdrant:chunks",
                "evidence",
                0.9,
                metadata={"knowledge_generation_id": scope.generation_id},
            )
        ]

    def search(self, *args, **kwargs):
        self.legacy_calls += 1
        raise AssertionError("V2 must not call legacy workspace retrieval")


def _plan(capability="retrieval.semantic_search"):
    retrieval = ExecutionStep(
        step_id="execute.retrieve",
        engine="retrieval",
        capability=capability,
        output_type="evidence_set",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace-a", generation_id="generation-42"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(
            logical_node_ids=("retrieve",), selection_reason="test generation-bound retrieval"
        ),
    )
    reconcile = ExecutionStep(
        step_id="execute.reconcile",
        engine="result_evidence",
        capability="evidence.reconcile_and_validate",
        dependencies=(retrieval.step_id,),
        input_types=("evidence_set",),
        output_type="evidence_package",
        coverage_expectation="grounded",
        readiness=ReadinessRequirement(workspace_id="workspace-a"),
        failure_policy=FailurePolicy(action="fail_closed"),
        trace=PlanTrace(
            logical_node_ids=("retrieve",), selection_reason="test reconciliation boundary"
        ),
    )
    return PhysicalExecutionPlan(
        workspace_id="workspace-a",
        state="ready",
        graph=ExecutionPlanGraph(steps=(retrieval, reconcile), root_step_ids=(reconcile.step_id,)),
    )


def test_physical_plan_reaches_generation_bound_dense_adapter_once():
    resolver = ScopeResolver()
    store = DenseStore()

    result = V2PlanExecutor(resolver, V2DenseAdapter(store)).execute(
        _plan(), [0.1, 0.2], dense_limit=3
    )

    assert resolver.calls == 1
    assert store.generation_calls == [
        ([0.1, 0.2], 3, GenerationScope("workspace-a", "generation-42", "embedding-hash"))
    ]
    assert store.legacy_calls == 0
    assert result.trace.workspace_id == "workspace-a"
    assert result.trace.generation_id == "generation-42"
    assert result.trace.embedding_config_hash == "embedding-hash"
    assert result.trace.engine == "retrieval.semantic_search"
    assert result.trace.result_count == 1


def _write(client, workspace, generation, embedding, record_id, content, vector):
    WorkspaceQdrantStore(
        client,
        workspace,
        embedding_config_hash=embedding,
        projection_key=generation,
    ).upsert(
        "chunks",
        [VectorRecord(record_id, vector, {"content": content, "chunk_id": record_id})],
        dimension=len(vector),
    )


def _execute(client, workspace, generation, embedding):
    resolver = ScopeResolver()
    resolver.resolve = lambda _: GenerationScope(workspace, generation, embedding)
    store = WorkspaceQdrantStore(client, workspace, embedding_config_hash=embedding)
    return V2PlanExecutor(resolver, V2DenseAdapter(store)).execute(
        _plan(), [1.0, 0.0], dense_limit=10
    )


def test_execution_excludes_other_generation_in_same_workspace():
    client = QdrantClient(":memory:")
    _write(client, "workspace-a", "generation-41", "hash-1", "old", "old", [1.0, 0.0])
    _write(client, "workspace-a", "generation-42", "hash-1", "new", "new", [0.1, 1.0])

    result = _execute(client, "workspace-a", "generation-42", "hash-1")

    assert [item.content for item in result.dense_evidence] == ["new"]


def test_execution_excludes_same_generation_from_other_workspace():
    client = QdrantClient(":memory:")
    _write(client, "workspace-a", "generation-42", "hash-1", "local", "local", [1.0, 0.0])
    _write(client, "workspace-b", "generation-42", "hash-1", "foreign", "foreign", [1.0, 0.0])

    result = _execute(client, "workspace-a", "generation-42", "hash-1")

    assert [item.content for item in result.dense_evidence] == ["local"]


def test_execution_excludes_same_generation_with_other_embedding_hash():
    client = QdrantClient(":memory:")
    _write(client, "workspace-a", "generation-42", "hash-1", "compatible", "compatible", [1.0, 0.0])
    _write(client, "workspace-a", "generation-42", "hash-2", "wrong", "wrong", [1.0, 0.0])

    result = _execute(client, "workspace-a", "generation-42", "hash-1")

    assert [item.content for item in result.dense_evidence] == ["compatible"]


def test_missing_or_invalid_generation_scope_fails_closed():
    try:
        GenerationScope("", "generation-42", "hash-1")
    except ValueError as error:
        assert str(error) == "GENERATION_SCOPE_REQUIRED"
    else:
        raise AssertionError("invalid generation scope was accepted")


def test_store_rejects_workspace_and_embedding_scope_mismatches():
    client = QdrantClient(":memory:")
    store = WorkspaceQdrantStore(client, "workspace-a", embedding_config_hash="hash-1")

    try:
        store.search_generation([1.0, 0.0], 1, GenerationScope("workspace-b", "g", "hash-1"))
    except ValueError as error:
        assert str(error) == "GENERATION_SCOPE_WORKSPACE_MISMATCH"
    else:
        raise AssertionError("workspace mismatch was accepted")
    try:
        store.search_generation([1.0, 0.0], 1, GenerationScope("workspace-a", "g", "hash-2"))
    except ValueError as error:
        assert str(error) == "EMBEDDING_FINGERPRINT_REQUIRED"
    else:
        raise AssertionError("embedding mismatch was accepted")


def test_returned_generation_mismatch_fails_closed():
    class MismatchedStore:
        def search_generation(self, query_vector, limit, scope):
            return [
                Evidence(
                    scope.workspace_id,
                    "qdrant:chunks",
                    "wrong",
                    1.0,
                    metadata={"knowledge_generation_id": "generation-41"},
                )
            ]

    try:
        V2DenseAdapter(MismatchedStore()).search(
            GenerationScope("workspace-a", "generation-42", "hash-1"), [1.0, 0.0], 1
        )
    except RuntimeError as error:
        assert str(error) == "GENERATION_MISMATCH"
    else:
        raise AssertionError("mismatched returned generation was accepted")


def test_empty_generation_results_do_not_use_legacy_search():
    class EmptyStore(DenseStore):
        def search_generation(self, query_vector, limit, scope):
            self.generation_calls.append((query_vector, limit, scope))
            return []

    store = EmptyStore()
    result = V2PlanExecutor(ScopeResolver(), V2DenseAdapter(store)).execute(
        _plan(), [1.0, 0.0], dense_limit=1
    )

    assert result.dense_evidence == ()
    assert store.legacy_calls == 0


def test_execution_scope_is_snapshot_when_active_pointer_changes():
    class MutableResolver:
        def __init__(self):
            self.active = "generation-42"

        def resolve(self, workspace_id):
            return GenerationScope(workspace_id, self.active, "hash-1")

    class PointerStore(DenseStore):
        def __init__(self, resolver):
            super().__init__()
            self.resolver = resolver

        def search_generation(self, query_vector, limit, scope):
            self.resolver.active = "generation-43"
            return super().search_generation(query_vector, limit, scope)

    resolver = MutableResolver()
    store = PointerStore(resolver)
    executor = V2PlanExecutor(resolver, V2DenseAdapter(store))

    first = executor.execute(_plan(), [1.0, 0.0], dense_limit=1)
    second = executor.execute(_plan(), [1.0, 0.0], dense_limit=1)

    assert first.trace.generation_id == "generation-42"
    assert store.generation_calls[0][2].generation_id == "generation-42"
    assert second.trace.generation_id == "generation-43"
