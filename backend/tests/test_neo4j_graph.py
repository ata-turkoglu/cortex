import json

import pytest

from app.graphrag.adapter import GraphRAGAdapter, GraphRoute
from app.graphrag.neo4j import Neo4jBackedGraphRAGAdapter
from app.knowledge.graph import GraphNode, GraphRelationship, GraphSyncResult, Neo4jGraphAdapter


class ConsumedResult:
    def consume(self):
        return None


class RecordingTransaction:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return ConsumedResult()


class RecordingSession:
    def __init__(self, driver, database):
        self.driver = driver
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute_write(self, callback, *args, **kwargs):
        transaction = RecordingTransaction()
        callback(transaction, *args, **kwargs)
        self.driver.transactions.append((self.database, transaction.calls))


class RecordingDriver:
    def __init__(self):
        self.transactions = []
        self.schema_calls = []
        self.node_count = 0
        self.verified = False
        self.closed = False
        self.curation_rows = []

    def session(self, *, database):
        return RecordingSession(self, database)

    def execute_query(self, query, **parameters):
        self.schema_calls.append((query, parameters))
        if "CortexIdentityOperation" in query and "ORDER BY kind, item_id" in query:
            return (self.curation_rows, None, ["kind", "item_id", "value"])
        if "RETURN count(n) AS node_count" in query:
            return ([{"node_count": self.node_count}], None, ["node_count"])
        return ([], None, [])

    def verify_connectivity(self):
        self.verified = True

    def close(self):
        self.closed = True


def test_neo4j_adapter_scopes_every_write_and_preserves_canonical_layer():
    driver = RecordingDriver()
    node_a = GraphNode("entity:a", "entities", "generation-1")
    node_b = GraphNode("entity:b", "entities", "generation-1")
    relationship = GraphRelationship(
        "relationship:1",
        "related",
        node_a.external_id,
        node_b.external_id,
        "generation-1",
    )

    first = Neo4jGraphAdapter("workspace-a", driver)
    second = Neo4jGraphAdapter("workspace-b", driver)
    first.ensure_schema()
    result = first.replace_extracted_generation(
        "generation-1", (node_a, node_b), (relationship,)
    )
    second.replace_extracted_generation("generation-1", (node_a, node_b), (relationship,))

    assert result == GraphSyncResult("workspace-a", "generation-1", 2, 1)
    assert len(driver.schema_calls) == 8
    for workspace_id, (_, calls) in zip(
        ("workspace-a", "workspace-b"), driver.transactions, strict=True
    ):
        assert all(call[1]["workspace_id"] == workspace_id for call in calls)
        assert "ExtractedKnowledge" in calls[0][0]
        assert "CanonicalKnowledge" not in calls[0][0]


def test_neo4j_adapter_rejects_cross_generation_or_missing_endpoints():
    adapter = Neo4jGraphAdapter("workspace-a", RecordingDriver())
    node = GraphNode("entity:a", "entities", "generation-1")
    wrong_generation = GraphNode("entity:b", "entities", "generation-2")
    with pytest.raises(ValueError, match="requested generation"):
        adapter.replace_extracted_generation(
            "generation-1", (node, wrong_generation), ()
        )
    with pytest.raises(ValueError, match="endpoints"):
        adapter.replace_extracted_generation(
            "generation-1",
            (node,),
            (
                GraphRelationship(
                    "relationship:1",
                    "related",
                    "entity:a",
                    "entity:missing",
                    "generation-1",
                ),
            ),
        )


def test_neo4j_adapter_scopes_extracted_count_to_workspace_and_generation():
    driver = RecordingDriver()
    driver.node_count = 7
    adapter = Neo4jGraphAdapter("workspace-a", driver)

    assert adapter.extracted_node_count("generation-1") == 7
    query, parameters = driver.schema_calls[-1]
    assert "workspace_id: $workspace_id" in query
    assert "generation: $generation" in query
    assert parameters["workspace_id"] == "workspace-a"
    assert parameters["generation"] == "generation-1"


def test_curation_fingerprint_is_deterministic_and_workspace_scoped():
    driver = RecordingDriver()
    driver.curation_rows = [
        {
            "kind": "alias",
            "item_id": "alias-1",
            "value": {"value": "A. Merter", "active": True},
        }
    ]
    adapter = Neo4jGraphAdapter("workspace-a", driver)

    first = adapter.curation_fingerprint()
    second = adapter.curation_fingerprint()

    assert first == second
    assert len(first) == 64
    query, parameters = driver.schema_calls[-1]
    assert "authority: 'user_curated'" in query
    assert parameters["workspace_id"] == "workspace-a"


class RecordingGraphStore:
    def __init__(self, workspace_id):
        self.workspace_id = workspace_id
        self.schema_ready = False
        self.synced = None

    def ensure_schema(self):
        self.schema_ready = True

    def replace_extracted_generation(self, generation, nodes, relationships):
        self.synced = (generation, nodes, relationships)
        return GraphSyncResult(self.workspace_id, generation, len(nodes), len(relationships))


def test_graphrag_extraction_syncs_to_neo4j_with_provenance_and_typed_findings(tmp_path):
    root = tmp_path / "graphrag"
    root.mkdir()
    logical_id = "11111111-1111-1111-1111-111111111111"
    (root / "entities.json").write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "text": "Ankara",
                    "attributes": {"title": "Ankara", "logical_document_id": logical_id},
                },
                {"id": "b", "text": "Türkiye", "attributes": {"title": "Türkiye"}},
            ]
        ),
        encoding="utf-8",
    )
    (root / "relationships.json").write_text(
        json.dumps(
            [
                {
                    "id": "r1",
                    "text": "başkentidir",
                    "attributes": {"source": "Ankara", "target": "Türkiye"},
                }
            ]
        ),
        encoding="utf-8",
    )
    for resource_type in ("reports", "text_units", "documents"):
        (root / f"{resource_type}.json").write_text("[]", encoding="utf-8")

    graphrag = GraphRAGAdapter("workspace-a", root)
    store = RecordingGraphStore("workspace-a")
    bridge = Neo4jBackedGraphRAGAdapter(graphrag, store)
    sync = bridge.sync_extracted("generation-1")
    output = bridge.query_findings(GraphRoute.LOCAL, "Ankara")

    assert store.schema_ready is True
    assert sync.graph.node_count == 2
    assert sync.graph.relationship_count == 1
    _, nodes, relationships = store.synced
    assert nodes[0].provenance["producer"] == "microsoft_graphrag"
    assert nodes[0].provenance["logical_document_ids"] == [logical_id]
    assert relationships[0].source_id == "entities:a"
    assert output.route is GraphRoute.LOCAL
    assert output.findings[0].text == "Ankara"
    assert output.final_answer_authored is False


def test_graphrag_and_neo4j_workspace_mismatch_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="same workspace"):
        Neo4jBackedGraphRAGAdapter(
            GraphRAGAdapter("workspace-a", tmp_path), RecordingGraphStore("workspace-b")
        )
