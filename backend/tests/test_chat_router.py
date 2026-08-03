from llama_index.core.tools import ToolMetadata

from app.chat.router import ROUTE_DESCRIPTIONS, ConstrainedSelector, LlamaIndexRouter, tool_catalog


def test_llamaindex_tool_catalog_has_distinct_route_descriptions():
    catalog = tool_catalog()
    assert {tool.metadata.name for tool in catalog.tools} == set(ROUTE_DESCRIPTIONS)
    assert all(tool.metadata.description for tool in catalog.tools)


def test_router_keeps_approved_multi_route_selection_constrained():
    result = LlamaIndexRouter().select("cross-document overview", "automatic")
    assert result.routes == ("hybrid", "graphrag_global")


def test_llamaindex_selector_returns_only_approved_tool_indexes():
    result = ConstrainedSelector(mode="deep_analysis").select(
        [
            ToolMetadata(name=name, description=description)
            for name, description in ROUTE_DESCRIPTIONS.items()
        ],
        "compare patterns",
    )
    assert len(result.selections) == 2
