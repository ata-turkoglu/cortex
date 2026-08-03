"""LlamaIndex query-engine wrappers for distinct GraphRAG routes."""
from llama_index.core.base.response.schema import Response
from llama_index.core.query_engine import CustomQueryEngine
from llama_index.core.schema import NodeWithScore, TextNode
from pydantic import ConfigDict

from .adapter import GraphRAGAdapter, GraphRoute


class GraphRAGQueryEngine(CustomQueryEngine):
    """Expose one GraphRAG route without flattening it into a basic retriever."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    adapter: GraphRAGAdapter
    route: GraphRoute
    limit: int = 10

    def custom_query(self, query_str: str) -> Response:
        result = self.adapter.query(self.route, query_str, self.limit)
        source_nodes = [
            NodeWithScore(
                node=TextNode(
                    id_=item.chunk_id or f"{self.route.value}:{position}",
                    text=item.content,
                    metadata={
                        "workspace_id": item.workspace_id,
                        "source": item.source,
                        "citation_label": item.citation_label,
                        **item.metadata,
                    },
                ),
                score=item.score,
            )
            for position, item in enumerate(result.evidence)
        ]
        response = "\n\n".join(item.content for item in result.evidence) or None
        return Response(
            response=response,
            source_nodes=source_nodes,
            metadata={"route": self.route.value, "answer_state": result.state.value},
        )
