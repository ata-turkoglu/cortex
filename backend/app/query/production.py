"""Production composition root for the detached Query V2 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qdrant_client import QdrantClient

from ..core.config import Settings, get_settings
from ..core.qdrant import get_qdrant_client
from ..graphrag.adapter import GraphRAGAdapter
from ..knowledge.canonical_completeness import CanonicalCompletenessEvaluator
from ..knowledge.canonical_reader import SQLiteCanonicalReader
from ..knowledge.graph import Neo4jConfigurationError, Neo4jGraphAdapter
from ..providers.base import EmbeddingProvider
from ..providers.embeddings import (
    EmbeddingConfiguration,
)
from ..retrieval.qdrant import WorkspaceQdrantStore
from ..retrieval.sparse import GenerationBM25Store
from .answer import AnswerEngine
from .briefing import build_workspace_briefing
from .execution import (
    ProductionEngineRegistry,
    RetrievalProductionEngine,
    V2DenseAdapter,
    V2PlanExecutor,
    V2SparseAdapter,
)
from .production_engines import (
    GraphProductionEngine,
    GraphRAGAdapterFactory,
    GraphRAGProductionEngine,
    StructuredProductionEngine,
)
from .runtime import QueryV2PreparationService, SemanticPlanner
from .runtime_inputs import V2RuntimeContextLoader, V2RuntimeInputs
from .scope import GenerationScope
from .service import V2QueryService
from .source_runtime import ConfiguredV2QueryEmbedder
from .understanding.planner import SemanticPlannerAdapter, planner_models

if TYPE_CHECKING:
    from .understanding.planner import StructuredPlannerProvider


class ProductionV2ConfigurationError(RuntimeError):
    """Configured production dependencies cannot satisfy the V2 contract."""


class V2QueryServiceFactory:
    """Own shared production dependencies and bind one immutable request scope.

    External model adapters are injectable for deterministic acceptance tests. With
    no overrides, this factory uses the same settings, cached Qdrant client, semantic
    planner, and embedding providers as the production backend.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        data_root: Path | None = None,
        qdrant_client: QdrantClient | None = None,
        planner: SemanticPlanner | None = None,
        planner_providers: dict[str, StructuredPlannerProvider] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_configuration: EmbeddingConfiguration | None = None,
        answer_engine: AnswerEngine | None = None,
        graphrag_adapter_factory: GraphRAGAdapterFactory | None = None,
        canonical_session=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.data_root = (data_root or self.settings.data_path).resolve()
        self.qdrant_client = qdrant_client or get_qdrant_client()
        self.context_loader = V2RuntimeContextLoader(
            history_limit=self.settings.conversation_memory_window_messages
        )
        self.planner = planner or self._configured_planner(planner_providers)
        self.preparation = QueryV2PreparationService(self.planner)
        if embedding_configuration is None:
            if settings is None:
                raise ProductionV2ConfigurationError(
                    "production query embeddings require persisted configuration"
                )
            if self.settings.embedding_provider is None or self.settings.embedding_model is None:
                raise ProductionV2ConfigurationError(
                    "production query embedding provider/model is missing"
                )
            embedding_configuration = EmbeddingConfiguration(
                self.settings.embedding_provider, self.settings.embedding_model
            )
        self.embedding_configuration = embedding_configuration
        if embedding_provider is None:
            raise ProductionV2ConfigurationError(
                "production query embeddings require the configured adapter"
            )
        provider = embedding_provider
        self.query_embedder = ConfiguredV2QueryEmbedder(provider, self.embedding_configuration)
        self.answer_engine = answer_engine or AnswerEngine()
        self.graphrag_adapter_factory = graphrag_adapter_factory or self._graphrag_adapter
        self.canonical_session = canonical_session

    def build(self, inputs: V2RuntimeInputs) -> V2QueryService:
        """Build a service whose retrieval stores are bound to ``inputs``."""
        scope = inputs.generation_scope
        if inputs.generation_scope_resolver.scope != scope:
            raise ValueError("runtime inputs contain inconsistent generation scope")
        dense_store = WorkspaceQdrantStore(
            self.qdrant_client,
            scope.workspace_id,
            embedding_config_hash=scope.embedding_config_hash,
            projection_key=scope.generation_id,
        )
        dense = V2DenseAdapter(dense_store)
        sparse = V2SparseAdapter(GenerationBM25Store(self.data_root))
        canonical_ready = any(
            item.engine == "structured"
            and item.capability == "structured.enumerate"
            and item.state == "ready"
            for item in inputs.readiness.capabilities
        )
        graph_ready = any(
            item.engine == "knowledge_graph" and item.state == "ready"
            for item in inputs.readiness.capabilities
        )

        def graph_reader(request_scope):
            return Neo4jGraphAdapter.from_settings(request_scope.workspace_id)

        def canonical_reader(request_scope):
            if self.canonical_session is not None:
                return SQLiteCanonicalReader(self.canonical_session, request_scope.workspace_id)
            from ..core.database import SessionLocal

            return SQLiteCanonicalReader(
                SessionLocal(), request_scope.workspace_id, owns_session=True
            )

        def briefing_loader(request_scope):
            # ``canonical.graph`` is intentionally unavailable until its
            # non-authoritative Neo4j projection has a production contract.
            # Do not probe Neo4j on grounded retrieval requests merely to
            # construct optional briefing context.
            if not graph_ready:
                return None
            try:
                with Neo4jGraphAdapter.from_settings(request_scope.workspace_id) as graph:
                    return build_workspace_briefing(graph, request_scope.generation_id, limit=100)
            except Neo4jConfigurationError:
                # Retrieval remains safely usable when canonical graph infrastructure is absent.
                return None

        def property_vocabulary_loader(request_scope):
            if not canonical_ready:
                return {}
            reader = canonical_reader(request_scope)
            try:
                return reader.queryable_property_vocabulary(request_scope.generation_id)
            finally:
                reader.close()

        def completeness_evaluator(request_scope, logical_ir, known_count):
            reader = canonical_reader(request_scope)
            try:
                return CanonicalCompletenessEvaluator(
                    reader.session, request_scope.workspace_id
                ).evaluate(request_scope.generation_id, logical_ir, known_count=known_count)
            finally:
                reader.close()

        registry = ProductionEngineRegistry(
            {
                "retrieval": RetrievalProductionEngine(dense, sparse),
                "structured": StructuredProductionEngine(canonical_reader),
                "knowledge_graph": GraphProductionEngine(graph_reader),
                "graphrag": GraphRAGProductionEngine(self.graphrag_adapter_factory),
            }
        )
        executor = V2PlanExecutor(inputs.generation_scope_resolver, dense, sparse, registry)
        return V2QueryService(
            self.preparation,
            inputs.generation_scope_resolver,
            self.query_embedder,
            executor,
            data_root=self.data_root,
            answer_engine=self.answer_engine,
            briefing_loader=briefing_loader,
            property_vocabulary_loader=property_vocabulary_loader,
            completeness_evaluator=completeness_evaluator,
        )

    def _graphrag_adapter(self, scope: GenerationScope) -> GraphRAGAdapter:
        root = (
            self.data_root
            / "workspaces"
            / scope.workspace_id
            / "knowledge-candidates"
            / scope.generation_id
            / "graphrag"
        ).resolve()
        expected_parent = (
            self.data_root / "workspaces" / scope.workspace_id / "knowledge-candidates"
        ).resolve()
        if expected_parent not in root.parents:
            raise ProductionV2ConfigurationError("GraphRAG generation root escapes workspace")
        return GraphRAGAdapter(scope.workspace_id, root)

    def _configured_planner(
        self,
        providers: dict[str, StructuredPlannerProvider] | None,
    ) -> SemanticPlannerAdapter:
        models = planner_models(self.settings)
        if providers is None:
            unsupported = sorted(
                {assignment.provider for assignment in models.values()} - {"openai"}
            )
            if unsupported:
                joined = ", ".join(unsupported)
                raise ProductionV2ConfigurationError(
                    f"configured semantic planner provider is unavailable: {joined}"
                )
        return SemanticPlannerAdapter(
            models=models,
            providers=providers,
            repair_attempts=self.settings.semantic_planner_repair_attempts,
            escalation_enabled=self.settings.semantic_planner_escalation_enabled,
            confidence_threshold=self.settings.semantic_planner_confidence_threshold,
        )


def build_v2_query_service(
    inputs: V2RuntimeInputs, *, factory: V2QueryServiceFactory | None = None
) -> V2QueryService:
    """Convenience entry point reusable by the later API cutover."""
    return (factory or V2QueryServiceFactory()).build(inputs)


def get_v2_query_service_factory() -> V2QueryServiceFactory:
    raise ProductionV2ConfigurationError(
        "build the V2 query factory from a request database session"
    )
