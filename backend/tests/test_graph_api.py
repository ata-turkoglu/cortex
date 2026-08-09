import json
from types import SimpleNamespace

from app.api.graph import graph_explorer


def test_graph_explorer_only_returns_relationships_between_visible_entities(tmp_path, monkeypatch):
    root = tmp_path / "graphrag"
    root.mkdir()
    (root / "entities.json").write_text(
        json.dumps(
            [
                {"id": "a", "text": "Ankara", "attributes": {"title": "Ankara"}},
                {"id": "b", "text": "Türkiye", "attributes": {"title": "Türkiye"}},
            ]
        ),
        encoding="utf-8",
    )
    (root / "relationships.json").write_text(
        json.dumps(
            [
                {"id": "a-b", "attributes": {"source": "a", "target": "b"}},
                {"id": "a-hidden", "attributes": {"source": "a", "target": "hidden"}},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.api.graph.WorkspaceContext.load",
        lambda *_: SimpleNamespace(
            graph_root=root,
            graphrag_state=SimpleNamespace(state="ready"),
        ),
    )

    result = graph_explorer("workspace-a", object())

    assert result.state == "ready"
    assert [node.label for node in result.nodes] == ["Ankara", "Türkiye"]
    assert [(edge.source, edge.target) for edge in result.edges] == [("a", "b")]
