import asyncio
import json

from qdrant_client import QdrantClient

from app.graphrag.adapter import GraphArtifact, GraphRAGAdapter
from app.graphrag.qdrant import GraphRAGQdrantAdapter, mirror_graph_outputs


def artifact(resource_type: str, artifact_id: str, text: str) -> GraphArtifact:
    return GraphArtifact(artifact_id, resource_type, text, {"title": artifact_id})


def test_graphrag_vector_types_are_separate_and_workspace_isolated():
    client = QdrantClient(":memory:")
    first = GraphRAGQdrantAdapter(client, "workspace-a")
    second = GraphRAGQdrantAdapter(client, "workspace-b")
    for resource_type in ("entities", "reports", "text_units"):
        first.index_artifacts(
            resource_type,
            [artifact(resource_type, f"a-{resource_type}", "first")],
            [[1.0, 0.0]],
            2,
        )
    second.index_artifacts(
        "entities",
        [artifact("entities", "b-entity", "second")],
        [[1.0, 0.0]],
        2,
    )
    assert [item.content for item in first.search("entities", [1.0, 0.0], 5)] == ["first"]
    assert [item.content for item in first.search("reports", [1.0, 0.0], 5)] == ["first"]
    assert [item.content for item in first.search("text_units", [1.0, 0.0], 5)] == ["first"]


def test_canonical_graph_outputs_are_mirrored_to_workspace_isolated_qdrant(tmp_path):
    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    for resource_type in ("entities", "reports", "text_units"):
        (root / f"{resource_type}.json").write_text(
            json.dumps(
                [{"id": resource_type, "text": f"{resource_type} text", "attributes": {}}]
            ),
            encoding="utf-8",
        )

    class Provider:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    graph = GraphRAGAdapter("workspace-a", root)
    mirror = GraphRAGQdrantAdapter(QdrantClient(":memory:"), "workspace-a")
    counts = asyncio.run(mirror_graph_outputs(graph, mirror, Provider()))
    assert counts == {"entities": 1, "reports": 1, "text_units": 1}
    assert mirror.search("reports", [1.0, 0.0], 1)[0].content == "reports text"
