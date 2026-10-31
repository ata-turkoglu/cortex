"""Physical, generation-bound Query V2 plan execution."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from app.retrieval.schemas import Evidence

from .ir.schemas import IRNode
from .orchestration import CompletenessReport, EngineFailure, EngineResult, EngineTrace
from .planning import ExecutionStep, PhysicalExecutionPlan
from .scope import GenerationScope


class GenerationScopeResolver(Protocol):
    def resolve(self, workspace_id: str) -> GenerationScope: ...


class GenerationDenseStore(Protocol):
    def search_generation(
        self, query_vector: list[float], limit: int, scope: GenerationScope
    ) -> list[Evidence]: ...


class GenerationSparseStore(Protocol):
    def search_generation(
        self, scope: GenerationScope, query: str, limit: int
    ) -> list[Evidence]: ...


@dataclass(frozen=True)
class V2DenseAdapter:
    store: GenerationDenseStore

    def search(
        self, scope: GenerationScope, query_vector: list[float], limit: int
    ) -> tuple[Evidence, ...]:
        evidence = tuple(
            item
            for item in self.store.search_generation(query_vector, limit, scope)
            if item.score > 0
        )
        if any(
            item.workspace_id != scope.workspace_id
            or item.metadata.get("knowledge_generation_id") != scope.generation_id
            for item in evidence
        ):
            raise RuntimeError("GENERATION_MISMATCH")
        return evidence


@dataclass(frozen=True)
class V2SparseAdapter:
    store: GenerationSparseStore

    def search(self, scope: GenerationScope, query: str, limit: int) -> tuple[Evidence, ...]:
        evidence = tuple(
            item for item in self.store.search_generation(scope, query, limit) if item.score > 0
        )
        if any(
            item.workspace_id != scope.workspace_id
            or item.metadata.get("knowledge_generation_id") != scope.generation_id
            for item in evidence
        ):
            raise RuntimeError("GENERATION_MISMATCH")
        return evidence


@dataclass(frozen=True)
class V2ExecutionTrace:
    workspace_id: str
    generation_id: str
    embedding_config_hash: str
    engine: str | None
    result_count: int
    sparse_engine: str | None = None
    sparse_result_count: int = 0
    sparse_artifact_identity: str | None = None


@dataclass(frozen=True)
class V2ExecutionResult:
    trace: V2ExecutionTrace
    dense_evidence: tuple[Evidence, ...] = ()
    sparse_evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class EngineExecutionContext:
    step: ExecutionStep
    node: IRNode
    scope: GenerationScope
    dependency_values: tuple[Any, ...]
    query_vector: list[float] | None
    query_text: str | None
    trusted_sources: tuple[Any, ...]
    dense_limit: int
    sparse_limit: int
    # Maximum fused retrieval candidates; ``None`` keeps every manifest-bound candidate.
    fusion_limit: int | None = None


@dataclass(frozen=True)
class EngineExecutionOutput:
    value: Any
    result: EngineResult


class ProductionQueryEngine(Protocol):
    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput: ...


class ProductionEngineRegistry:
    """Explicit, request-scoped dispatch boundary for V2 physical engines."""

    def __init__(self, engines: dict[str, ProductionQueryEngine]) -> None:
        self._engines = dict(engines)

    def engine_for(self, name: str) -> ProductionQueryEngine:
        try:
            return self._engines[name]
        except KeyError as error:
            raise ValueError(f"V2_ENGINE_NOT_REGISTERED:{name}") from error


class RetrievalProductionEngine:
    def __init__(self, dense: V2DenseAdapter, sparse: V2SparseAdapter | None) -> None:
        self.dense = dense
        self.sparse = sparse

    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput:
        if context.query_vector is None:
            raise ValueError("V2_RETRIEVAL_VECTOR_REQUIRED")
        started = perf_counter()
        dense = self.dense.search(context.scope, context.query_vector, context.dense_limit)
        sparse: tuple[Evidence, ...] = ()
        if context.step.capability == "retrieval.hybrid_search":
            if self.sparse is None or context.query_text is None:
                raise ValueError("GENERATION_BM25_NOT_READY")
            sparse = self.sparse.search(context.scope, context.query_text, context.sparse_limit)
        raw = V2ExecutionResult(
            V2ExecutionTrace(
                context.scope.workspace_id,
                context.scope.generation_id,
                context.scope.embedding_config_hash,
                context.step.capability,
                len(dense),
                "sparse/bm25" if sparse else None,
                len(sparse),
                f"{context.scope.workspace_id}:{context.scope.generation_id}:bm25"
                if sparse
                else None,
            ),
            dense,
            sparse,
        )
        # ``bridge_retrieval`` only needs the one declared retrieval step.
        plan = type(
            "RetrievalPlan", (), {"graph": type("Graph", (), {"steps": (context.step,)})()}
        )()
        from .orchestration.retrieval_bridge import bridge_retrieval

        source_count = len(context.trusted_sources)
        bridge = bridge_retrieval(
            plan,
            raw,
            context.scope,
            context.trusted_sources,
            limit=max(1, min(context.fusion_limit or source_count, source_count)),
        )
        result = bridge.engine_result.model_copy(
            update={
                "trace": bridge.engine_result.trace.model_copy(
                    update={"duration_ms": int((perf_counter() - started) * 1_000)}
                )
            }
        )
        return EngineExecutionOutput(None, result)


class UnavailableProductionEngine:
    """Registered but fail-closed until an engine can satisfy exact provenance."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason

    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput:
        result = EngineResult(
            result_id=f"failed-{context.step.step_id}",
            workspace_id=context.scope.workspace_id,
            generation_id=context.scope.generation_id,
            step_id=context.step.step_id,
            engine=context.step.engine,
            capability=context.step.capability,
            state="failed",
            completeness=CompletenessReport(
                coverage=context.step.coverage_expectation,
                state="unknown",
                generation_id=context.scope.generation_id,
            ),
            confidence=0.0,
            failures=(
                EngineFailure(
                    step_id=context.step.step_id,
                    engine=self.name,
                    capability=context.step.capability,
                    reason=self.reason,
                ),
            ),
            trace=EngineTrace(
                step_id=context.step.step_id,
                engine=context.step.engine,
                capability=context.step.capability,
                duration_ms=0,
            ),
        )
        return EngineExecutionOutput(None, result)


@dataclass(frozen=True)
class V2PlanExecution:
    scope: GenerationScope
    results: tuple[EngineResult, ...]
    values: dict[str, Any]
    skipped_step_ids: tuple[str, ...]


class V2PlanExecutor:
    """Execute every material step of a validated DAG in dependency order."""

    def __init__(
        self,
        scope_resolver: GenerationScopeResolver,
        dense: V2DenseAdapter,
        sparse: V2SparseAdapter | None = None,
        registry: ProductionEngineRegistry | None = None,
    ) -> None:
        self.scope_resolver = scope_resolver
        self.dense = dense
        self.sparse = sparse
        self.registry = registry or ProductionEngineRegistry(
            {"retrieval": RetrievalProductionEngine(dense, sparse)}
        )

    def execute_plan(
        self,
        plan: PhysicalExecutionPlan,
        nodes: tuple[IRNode, ...],
        *,
        query_vector: list[float] | None,
        query_text: str | None,
        trusted_sources: tuple[Any, ...],
        dense_limit: int = 30,
        sparse_limit: int = 30,
        fusion_limit: int | None = None,
    ) -> V2PlanExecution:
        if plan.state != "ready" or plan.graph is None:
            raise ValueError("V2 executor requires a ready physical execution plan")
        scope = self.scope_resolver.resolve(plan.workspace_id)
        if scope.workspace_id != plan.workspace_id:
            raise ValueError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        node_by_id = {node.node_id: node for node in nodes}
        values: dict[str, Any] = {}
        results: list[EngineResult] = []
        skipped: list[str] = []
        pending = {step.step_id: step for step in plan.graph.steps}
        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dep in values or dep in skipped for dep in step.dependencies)
            ]
            if not ready:
                raise ValueError("V2_EXECUTION_PLAN_DEPENDENCY_INVALID")
            for step in ready:
                pending.pop(step.step_id)
                if step.engine in {"result_evidence", "reasoning"}:
                    skipped.append(step.step_id)
                    continue
                node_ids = step.trace.logical_node_ids
                if len(node_ids) != 1 or node_ids[0] not in node_by_id:
                    raise ValueError(f"V2_EXECUTION_NODE_BINDING_INVALID:{step.step_id}")
                context = EngineExecutionContext(
                    step,
                    node_by_id[node_ids[0]],
                    scope,
                    tuple(values[item] for item in step.dependencies if item in values),
                    query_vector,
                    query_text,
                    trusted_sources,
                    dense_limit,
                    sparse_limit,
                    fusion_limit,
                )
                output = self.registry.engine_for(step.engine).execute(context)
                values[step.step_id] = output.value
                results.append(output.result)
                if output.result.state == "failed" and step.failure_policy.action == "fail_closed":
                    raise RuntimeError(f"V2_REQUIRED_ENGINE_FAILED:{step.step_id}")
        return V2PlanExecution(scope, tuple(results), values, tuple(skipped))

    def execute(
        self,
        plan: PhysicalExecutionPlan,
        query_vector: list[float],
        *,
        dense_limit: int,
        query_text: str | None = None,
        sparse_limit: int | None = None,
    ) -> V2ExecutionResult:
        """Compatibility retrieval-only API; production uses ``execute_plan``."""
        if plan.state != "ready" or plan.graph is None:
            raise ValueError("V2 executor requires a ready physical execution plan")
        scope = self.scope_resolver.resolve(plan.workspace_id)
        steps = [step for step in plan.graph.steps if step.engine == "retrieval"]
        if len(steps) != 1:
            raise ValueError("minimal compatibility executor supports exactly one retrieval step")
        dense = self.dense.search(scope, query_vector, dense_limit)
        sparse: tuple[Evidence, ...] = ()
        if steps[0].capability == "retrieval.hybrid_search":
            if self.sparse is None or query_text is None:
                raise ValueError("GENERATION_BM25_NOT_READY")
            sparse = self.sparse.search(scope, query_text, sparse_limit or dense_limit)
        return V2ExecutionResult(
            V2ExecutionTrace(
                scope.workspace_id,
                scope.generation_id,
                scope.embedding_config_hash,
                steps[0].capability,
                len(dense),
                "sparse/bm25" if sparse else None,
                len(sparse),
                f"{scope.workspace_id}:{scope.generation_id}:bm25" if sparse else None,
            ),
            dense,
            sparse,
        )
