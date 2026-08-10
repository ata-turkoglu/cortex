import json
import os
from io import BytesIO

import pytest
import yaml

from app.graphrag.adapter import GraphRAGAdapter, GraphRoute
from app.graphrag.cli import normalize_arrow_values
from app.graphrag.input import GraphRAGInputMaterializer
from app.graphrag.llamaindex import GraphRAGQueryEngine
from app.retrieval.schemas import AnswerState


def test_graphrag_cli_normalizes_nested_arrow_arrays_before_writing_parquet():
    import pandas as pd
    import pyarrow as pa

    table = pd.DataFrame({"entity_ids": [pa.array(["entity-a", "entity-b"])]})
    normalized = normalize_arrow_values(table)

    assert normalized.loc[0, "entity_ids"] == ["entity-a", "entity-b"]
    normalized.to_parquet(BytesIO())


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


def test_runner_keeps_the_actionable_tail_of_a_graphrag_failure(monkeypatch, tmp_path):
    from app.graphrag.adapter import GraphRAGExecutionError, MicrosoftGraphRAGRunner

    class Completed:
        returncode = 1
        stdout = ""
        stderr = "traceback start\n" + ("x" * 2000) + "\nValueError: actionable cause"

    monkeypatch.setattr("app.graphrag.adapter.SecretStore.get", lambda *_: "configured")
    monkeypatch.setattr(
        "app.graphrag.adapter.subprocess.run", lambda *_args, **_kwargs: Completed()
    )
    with pytest.raises(GraphRAGExecutionError, match="ValueError: actionable cause") as error:
        MicrosoftGraphRAGRunner()._run(["index"], tmp_path)
    assert "traceback start" not in str(error.value)


def test_runner_adds_the_cortex_package_root_for_the_worker_cli(monkeypatch, tmp_path):
    from app.graphrag.adapter import MicrosoftGraphRAGRunner

    captured = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("app.graphrag.adapter.SecretStore.get", lambda *_: "configured")
    monkeypatch.setattr(
        "app.graphrag.adapter.subprocess.run",
        lambda *_args, **kwargs: captured.update(kwargs) or Completed(),
    )

    MicrosoftGraphRAGRunner()._run(["index"], tmp_path)

    assert captured["env"]["PYTHONPATH"].split(os.pathsep)[0].endswith("backend")


def test_graph_adapter_updates_the_generated_model_placeholder_without_storing_secrets(tmp_path):
    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    config = root / "settings.yaml"
    config.write_text(
        "model: gpt-4-turbo-preview\n"
        "# encoding_model: cl100k_base # automatically set by tiktoken if left undefined\n",
        encoding="utf-8",
    )

    class Runner:
        def index(self, *_):
            pass

    adapter = GraphRAGAdapter("workspace-a", root, config_path=config, runner=Runner())
    adapter.index()

    assert "gpt-4-turbo-preview" not in config.read_text(encoding="utf-8")
    assert "encoding_model: cl100k_base" in config.read_text(encoding="utf-8")


def test_graph_adapter_sets_a_concrete_chat_token_limit(tmp_path):
    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    config = root / "settings.yaml"
    config.write_text(
        "models:\n"
        "  default_chat_model:\n"
        "    model_supports_json: true # recommended if this is available for your model.\n"
        "  default_embedding_model:\n",
        encoding="utf-8",
    )

    class Runner:
        def index(self, *_):
            pass

    GraphRAGAdapter("workspace-a", root, config_path=config, runner=Runner()).index()
    configured = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert configured["models"]["default_chat_model"]["max_tokens"] == 4096
    assert configured["models"]["default_embedding_model"]["encoding_model"] == "cl100k_base"
    assert configured["input"] == {"file_type": "text", "file_pattern": r".*\.md\Z"}


def test_graph_adapter_replaces_upstream_default_chat_model_with_selected_extraction_model(
    monkeypatch, tmp_path
):
    from app.core.config import Settings

    root = tmp_path / "workspace" / "graphrag"
    root.mkdir(parents=True)
    config = root / "settings.yaml"
    config.write_text(
        "models:\n  default_chat_model:\n    model: gpt-4-turbo-preview\n",
        encoding="utf-8",
    )

    class Runner:
        def index(self, *_):
            pass

    monkeypatch.setattr(
        "app.graphrag.adapter.get_settings",
        lambda: Settings(
            graphrag_extraction_provider="ollama",
            graphrag_extraction_model="selected-local-model",
            ollama_base_url="http://ollama.example/",
        ),
    )
    GraphRAGAdapter("workspace-a", root, config_path=config, runner=Runner()).index()

    configured = yaml.safe_load(config.read_text(encoding="utf-8"))
    default_chat = configured["models"]["default_chat_model"]
    assert default_chat["model"] == "selected-local-model"
    assert default_chat["api_base"] == "http://ollama.example/v1"


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
