"""Production adapters from a physical V2 step to existing typed engines."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from time import perf_counter

from app.engines.graph import GraphValue, KnowledgeGraphEngine
from app.engines.structured import StructuredQueryEngine, StructuredValue, load_canonical_population
from app.graphrag.adapter import GraphRAGAdapter, GraphRoute
from app.query.ir.schemas import EventSetNode, ScanNode
from app.query.orchestration import CompletenessReport, EngineResult, EngineTrace

from .execution import EngineExecutionContext, EngineExecutionOutput
from .orchestration.graphrag_bridge import bridge_graphrag
from .scope import GenerationScope

GraphReaderFactory = Callable[[GenerationScope], object]
GraphRAGAdapterFactory = Callable[[GenerationScope], GraphRAGAdapter]


class StructuredProductionEngine:
    """Run canonical structured operations with an exact request generation."""

    def __init__(self, reader_factory: GraphReaderFactory) -> None:
        self.reader_factory = reader_factory

    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput:
        # Document scans are the planner's non-material retrieval prerequisite.  They do not
        # claim a canonical population and therefore cannot be substituted for an entity scan.
        if isinstance(context.node, ScanNode) and context.node.resource == "document":
            return EngineExecutionOutput(None, _source_scan_result(context))
        reader = self.reader_factory(context.scope)
        try:
            population = (
                load_canonical_population(
                    reader, context.scope.generation_id, context.node.resource
                )
                if isinstance(context.node, ScanNode)
                else None
            )
            value, result = StructuredQueryEngine(
                context.scope.workspace_id, context.scope.generation_id
            ).execute(
                context.step,
                context.node,
                tuple(
                    item for item in context.dependency_values if isinstance(item, StructuredValue)
                ),
                population=population,
            )
            return EngineExecutionOutput(value, result)
        finally:
            with suppress(AttributeError):
                reader.close()


class GraphProductionEngine:
    """Run canonical graph operations only through the Cortex graph adapter."""

    def __init__(self, reader_factory: GraphReaderFactory) -> None:
        self.reader_factory = reader_factory

    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput:
        # The EventSet node is a logical population anchor for graph.event_filter.  The
        # material filter performs the one authoritative adapter read, so this prerequisite
        # must not enumerate every event or open a graph client.
        if isinstance(context.node, EventSetNode):
            return EngineExecutionOutput(GraphValue(), _event_population_result(context))
        reader = self.reader_factory(context.scope)
        try:
            value, result = KnowledgeGraphEngine(
                context.scope.workspace_id, context.scope.generation_id, reader
            ).execute(
                context.step,
                context.node,
                tuple(item for item in context.dependency_values if isinstance(item, GraphValue)),
            )
            return EngineExecutionOutput(value, result)
        finally:
            with suppress(AttributeError):
                reader.close()


class GraphRAGProductionEngine:
    """Read only generation-bound, provenance-bearing GraphRAG artifacts."""

    def __init__(self, adapter_factory: GraphRAGAdapterFactory) -> None:
        self.adapter_factory = adapter_factory

    def execute(self, context: EngineExecutionContext) -> EngineExecutionOutput:
        try:
            mode = GraphRoute(context.step.capability.removeprefix("graphrag."))
        except ValueError as error:
            raise ValueError(f"GRAPHRAG_MODE_UNSUPPORTED:{context.step.capability}") from error
        adapter = self.adapter_factory(context.scope)
        candidates = adapter.query_findings(
            mode, context.query_text or "", context.scope.generation_id
        )
        return bridge_graphrag(context, candidates)


def _source_scan_result(context: EngineExecutionContext) -> EngineResult:
    started = perf_counter()
    return EngineResult(
        result_id=f"source-scan-{context.step.step_id}",
        workspace_id=context.scope.workspace_id,
        generation_id=context.scope.generation_id,
        step_id=context.step.step_id,
        engine=context.step.engine,
        capability=context.step.capability,
        state="success",
        completeness=CompletenessReport(
            coverage="grounded",
            state="unknown",
            generation_id=context.scope.generation_id,
            ready_projections=("source_relational",),
        ),
        confidence=1.0,
        trace=EngineTrace(
            step_id=context.step.step_id,
            engine=context.step.engine,
            capability=context.step.capability,
            duration_ms=int((perf_counter() - started) * 1_000),
        ),
    )


def _event_population_result(context: EngineExecutionContext) -> EngineResult:
    started = perf_counter()
    return EngineResult(
        result_id=f"event-population-{context.step.step_id}",
        workspace_id=context.scope.workspace_id,
        generation_id=context.scope.generation_id,
        step_id=context.step.step_id,
        engine=context.step.engine,
        capability=context.step.capability,
        state="success",
        completeness=CompletenessReport(
            coverage="grounded",
            state="unknown",
            generation_id=context.scope.generation_id,
        ),
        confidence=1.0,
        trace=EngineTrace(
            step_id=context.step.step_id,
            engine=context.step.engine,
            capability=context.step.capability,
            duration_ms=int((perf_counter() - started) * 1_000),
        ),
    )
