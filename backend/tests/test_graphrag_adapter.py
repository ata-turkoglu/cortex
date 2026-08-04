import json

from app.graphrag.adapter import GraphRAGAdapter, GraphRoute
from app.graphrag.input import GraphRAGInputMaterializer
from app.graphrag.llamaindex import GraphRAGQueryEngine
from app.retrieval.schemas import AnswerState


def test_graphrag_routes_remain_distinct_and_networkx_is_rebuildable(tmp_path):
    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    (root / "entities.json").write_text(
        json.dumps(
            [{"id": "a", "text": "Ankara Türkiye başkenti", "attributes": {"title": "Ankara"}}]
        ),
        encoding="utf-8",
    )
    (root / "reports.json").write_text(
        json.dumps([{"id": "r", "text": "Türkiye özeti", "attributes": {"title": "Rapor"}}]),
        encoding="utf-8",
    )
    (root / "relationships.json").write_text(
        json.dumps([{"id": "rel", "text": "", "attributes": {"source": "a", "target": "b"}}]),
        encoding="utf-8",
    )
    adapter = GraphRAGAdapter("workspace-a", root)
    assert adapter.query(GraphRoute.LOCAL, "Ankara").evidence[0].source == "graphrag:local"
    assert adapter.query(GraphRoute.GLOBAL, "Türkiye").evidence[0].source == "graphrag:global"
    assert adapter.query(GraphRoute.DRIFT, "Türkiye").evidence[0].source == "graphrag:drift"
    assert adapter.rebuild_networkx().number_of_edges() == 1
    assert (root / "networkx.graphml").exists()


def test_missing_graph_is_an_explicit_fallback(tmp_path):
    adapter = GraphRAGAdapter("workspace-a", tmp_path / "missing")
    result = adapter.query(GraphRoute.LOCAL, "anything")
    assert result.state is AnswerState.UNSUPPORTED
    assert result.fallback_reason == "graph_not_indexed"


def test_graph_adapter_delegates_index_and_distinct_routes_to_upstream_runner(tmp_path):
    calls = []

    class Runner:
        def initialize(self, root):
            config = root / "settings.yaml"
            config.write_text("models: {}", encoding="utf-8")
            calls.append(("initialize", root))
            return config

        def index(self, root, config, method):
            calls.append(("index", root, config, method))

        def query(self, root, config, route, query):
            calls.append(("query", root, config, route, query))
            return f"{route.value}: {query}"

    root = tmp_path / "workspace" / "graphrag"
    adapter = GraphRAGAdapter("workspace-a", root, runner=Runner())
    config = adapter.initialize()
    adapter.index("fast")
    (root / "output" / "artifacts.parquet").touch()
    local = adapter.query(GraphRoute.LOCAL, "Ankara")
    global_result = adapter.query(GraphRoute.GLOBAL, "Türkiye")
    drift = adapter.query(GraphRoute.DRIFT, "Neden?")
    assert calls[0][0] == "initialize"
    assert calls[1][0] == "index"
    assert calls[1][2] == config
    assert [call[3] for call in calls[2:]] == [
        GraphRoute.LOCAL,
        GraphRoute.GLOBAL,
        GraphRoute.DRIFT,
    ]
    assert local.evidence[0].content == "local: Ankara"
    assert global_result.evidence[0].content == "global: Türkiye"
    assert drift.evidence[0].content == "drift: Neden?"


def test_graph_adapter_reads_native_parquet_outputs_without_rewriting_them(tmp_path):
    import pandas as pd

    root = tmp_path / "workspace" / "graphrag"
    output = root / "output"
    output.mkdir(parents=True)
    pd.DataFrame(
        [{"id": "entity-1", "title": "Ankara", "description": "Türkiye'nin başkenti"}]
    ).to_parquet(output / "create_final_entities.parquet")
    artifacts = GraphRAGAdapter("workspace-a", root).load_artifacts("entities")
    assert artifacts[0].artifact_id == "entity-1"
    assert artifacts[0].text == "Türkiye'nin başkenti"
    assert artifacts[0].attributes["title"] == "Ankara"


def test_llamaindex_query_engines_keep_graphrag_routes_and_evidence_distinct(tmp_path):
    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    (root / "entities.json").write_text(
        json.dumps([{"id": "a", "text": "Ankara", "attributes": {"title": "Başkent"}}]),
        encoding="utf-8",
    )
    adapter = GraphRAGAdapter("workspace-a", root)
    response = GraphRAGQueryEngine(adapter=adapter, route=GraphRoute.LOCAL).query("Ankara")
    assert response.metadata == {"route": "local", "answer_state": "grounded"}
    assert response.source_nodes[0].node.metadata["workspace_id"] == "workspace-a"


def test_failed_upstream_query_is_an_explicit_stale_graph_fallback(tmp_path):
    from app.graphrag.adapter import GraphRAGExecutionError

    class FailingRunner:
        def index(self, root, config, method):
            pass

        def query(self, root, config, route, query):
            raise GraphRAGExecutionError("provider unavailable")

    root = tmp_path / "workspace" / "graphrag"
    output = root / "output"
    output.mkdir(parents=True)
    (output / "create_final_entities.parquet").touch()
    result = GraphRAGAdapter(
        "workspace-a", root, config_path=root / "settings.yaml", runner=FailingRunner()
    ).query(GraphRoute.LOCAL, "Ankara")
    assert result.state is AnswerState.UNSUPPORTED
    assert result.fallback_reason == "graph_stale"


def test_graphrag_input_materializer_copies_only_active_workspace_documents(tmp_path):
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Document, DocumentVersion, Workspace

    data_root = tmp_path / "data"
    source = data_root / "normalized" / "active.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Ankara\nTürkiye'nin başkenti", encoding="utf-8")
    session = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(session.bind)
    now = datetime.now(UTC)
    workspace_id = str(uuid4())
    other_workspace_id = str(uuid4())
    active_document = Document(
        id=str(uuid4()), workspace_id=workspace_id, title="Active", created_at=now, updated_at=now
    )
    foreign_document = Document(
        id=str(uuid4()),
        workspace_id=other_workspace_id,
        title="Foreign",
        created_at=now,
        updated_at=now,
    )
    session.add_all(
        [
            Workspace(
                id=workspace_id,
                slug="active",
                name="Active",
                state="active",
                created_at=now,
                updated_at=now,
            ),
            Workspace(
                id=other_workspace_id,
                slug="foreign",
                name="Foreign",
                state="active",
                created_at=now,
                updated_at=now,
            ),
            active_document,
            foreign_document,
            DocumentVersion(
                id="active-version",
                workspace_id=workspace_id,
                document_id=active_document.id,
                version_number=1,
                source_hash="active-source",
                source_path="uploads/active.md",
                normalized_path="normalized/active.md",
                source_filename="active.md",
                size_bytes=1,
                state="ready",
                created_at=now,
            ),
            DocumentVersion(
                id="foreign-version",
                workspace_id=other_workspace_id,
                document_id=foreign_document.id,
                version_number=1,
                source_hash="foreign-source",
                source_path="uploads/foreign.md",
                normalized_path="normalized/active.md",
                source_filename="foreign.md",
                size_bytes=1,
                state="ready",
                created_at=now,
            ),
        ]
    )
    session.commit()
    manifest = GraphRAGInputMaterializer(data_root).materialize(
        session, workspace_id, tmp_path / "workspace" / "graphrag"
    )
    assert manifest.document_version_ids == ("active-version",)
    materialized = (manifest.input_root / "active-version.md").read_text(encoding="utf-8")
    assert materialized == source.read_text(encoding="utf-8")
    assert not (manifest.input_root / "foreign-version.md").exists()
