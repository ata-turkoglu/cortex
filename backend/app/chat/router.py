"""LlamaIndex tool catalog and constrained route selector for workspace chat."""

from dataclasses import dataclass

from llama_index.core.base.base_selector import BaseSelector, SelectorResult, SingleSelection
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from .service import RouteSelection, select_routes

ROUTE_DESCRIPTIONS = {
    "hybrid": "Search workspace document passages with dense and sparse retrieval.",
    "graphrag_local": "Answer entity-centred questions from the workspace GraphRAG local graph.",
    "graphrag_global": (
        "Answer cross-document and thematic questions from GraphRAG community reports."
    ),
    "graphrag_drift": "Explore a focused GraphRAG question with iterative follow-up retrieval.",
}


@dataclass(frozen=True)
class RoutedTools:
    """The LlamaIndex-compatible tool declarations exposed to a future provider selector."""

    tools: tuple[QueryEngineTool, ...]


def tool_catalog() -> RoutedTools:
    # Query engines are bound by the workspace execution adapter, never globally here.
    return RoutedTools(
        tuple(
            QueryEngineTool(
                query_engine=None,  # type: ignore[arg-type]
                metadata=ToolMetadata(name=route, description=description),
            )
            for route, description in ROUTE_DESCRIPTIONS.items()
        )
    )


class LlamaIndexRouter:
    """Constrain LlamaIndex route tools to V1's approved single/multi-route policy.

    A provider-backed `RouterQueryEngine` will consume this tool catalog once the provider
    request adapter is enabled. The deterministic selector is deliberately retained as the
    non-network fallback, keeping route behavior testable and safe before configuration.
    """

    def select(self, query: str, mode: str) -> RouteSelection:
        return select_routes(query, mode)

    def build_engine(
        self, query_engine_tools: tuple[QueryEngineTool, ...], mode: str
    ) -> RouterQueryEngine:
        """Create an actual LlamaIndex RouterQueryEngine with the constrained selector."""
        return RouterQueryEngine(
            selector=ConstrainedSelector(mode=mode), query_engine_tools=query_engine_tools
        )


class ConstrainedSelector(BaseSelector):
    """Map V1's route policy into the LlamaIndex selector contract."""

    def __init__(self, mode: str = "automatic") -> None:
        self.mode = mode

    def _select(self, choices: list[ToolMetadata], query: QueryBundle) -> SelectorResult:
        selection = select_routes(query.query_str, self.mode)
        indexes = [index for index, choice in enumerate(choices) if choice.name in selection.routes]
        if not indexes:
            indexes = [0]
        return SelectorResult(
            selections=[SingleSelection(index=index, reason=selection.reason) for index in indexes]
        )

    async def _aselect(self, choices: list[ToolMetadata], query: QueryBundle) -> SelectorResult:
        return self._select(choices, query)

    def _get_prompts(self):
        return {}

    def _update_prompts(self, prompts):
        return None
