"""Dormant V2 physical-plan execution boundary.

This intentionally executes only generation-bound retrieval reads. It is internal
and testable; production chat routing, fusion, reconciliation, and answer rendering
stay outside this batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.retrieval.schemas import Evidence

from .planning import PhysicalExecutionPlan
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
    """The sole dense retrieval adapter used by the dormant V2 executor."""

    store: GenerationDenseStore

    def search(
        self, scope: GenerationScope, query_vector: list[float], limit: int
    ) -> tuple[Evidence, ...]:
        evidence = tuple(self.store.search_generation(query_vector, limit, scope))
        if any(
            item.metadata.get("knowledge_generation_id") != scope.generation_id
            for item in evidence
        ):
            raise RuntimeError("GENERATION_MISMATCH")
        return evidence


@dataclass(frozen=True)
class V2SparseAdapter:
    """The sole sparse retrieval adapter used by the dormant V2 executor."""

    store: GenerationSparseStore

    def search(
        self, scope: GenerationScope, query: str, limit: int
    ) -> tuple[Evidence, ...]:
        evidence = tuple(self.store.search_generation(scope, query, limit))
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
    """Non-user-facing internal result; it is not an EngineResult or an answer."""

    trace: V2ExecutionTrace
    dense_evidence: tuple[Evidence, ...] = ()
    sparse_evidence: tuple[Evidence, ...] = ()


class V2PlanExecutor:
    """Execute the retrieval step declared by an existing PhysicalExecutionPlan."""

    def __init__(
        self,
        scope_resolver: GenerationScopeResolver,
        dense: V2DenseAdapter,
        sparse: V2SparseAdapter | None = None,
    ) -> None:
        self.scope_resolver = scope_resolver
        self.dense = dense
        self.sparse = sparse

    def execute(
        self,
        plan: PhysicalExecutionPlan,
        query_vector: list[float],
        *,
        dense_limit: int,
        query_text: str | None = None,
        sparse_limit: int | None = None,
    ) -> V2ExecutionResult:
        if plan.state != "ready" or plan.graph is None:
            raise ValueError("V2 executor requires a ready physical execution plan")
        if dense_limit < 1:
            raise ValueError("dense_limit must be positive")
        # Resolve exactly once; every engine receives this immutable snapshot.
        scope = self.scope_resolver.resolve(plan.workspace_id)
        if scope.workspace_id != plan.workspace_id:
            raise ValueError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        retrieval_steps = tuple(
            step
            for step in plan.graph.steps
            if step.engine == "retrieval"
            and step.capability in {"retrieval.hybrid_search", "retrieval.semantic_search"}
        )
        if not retrieval_steps:
            return V2ExecutionResult(
                trace=V2ExecutionTrace(
                    workspace_id=scope.workspace_id,
                    generation_id=scope.generation_id,
                    embedding_config_hash=scope.embedding_config_hash,
                    engine=None,
                    result_count=0,
                )
            )
        if len(retrieval_steps) != 1:
            raise ValueError("minimal V2 executor supports exactly one retrieval step")
        evidence = self.dense.search(scope, query_vector, dense_limit)
        step = retrieval_steps[0]
        sparse_evidence: tuple[Evidence, ...] = ()
        sparse_engine = None
        sparse_artifact_identity = None
        if step.capability == "retrieval.hybrid_search":
            if self.sparse is None or query_text is None:
                raise ValueError("GENERATION_BM25_NOT_READY")
            sparse_evidence = self.sparse.search(
                scope, query_text, sparse_limit if sparse_limit is not None else dense_limit
            )
            sparse_engine = "sparse/bm25"
            sparse_artifact_identity = f"{scope.workspace_id}:{scope.generation_id}:bm25"
        return V2ExecutionResult(
            trace=V2ExecutionTrace(
                workspace_id=scope.workspace_id,
                generation_id=scope.generation_id,
                embedding_config_hash=scope.embedding_config_hash,
                engine=step.capability,
                result_count=len(evidence),
                sparse_engine=sparse_engine,
                sparse_result_count=len(sparse_evidence),
                sparse_artifact_identity=sparse_artifact_identity,
            ),
            dense_evidence=evidence,
            sparse_evidence=sparse_evidence,
        )
