import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.graphrag import smart_search
from app.graphrag.adapter import GraphRAGAdapter, GraphRoute, route_model_family
from app.graphrag.smart_search import SmartSelection
from app.models import Base, UsageEvent
from app.query.orchestration import EngineTrace, TrustedSource
from app.query.production_chat import _record_graphrag_usage
from app.query.production_engines import GraphRAGProductionEngine
from app.query.scope import GenerationScope
from tests.test_graphrag_adapter import _write_native_output

CONTENT = "Ali Merter Moda tapusunu aldı."


def _source():
    return TrustedSource(
        workspace_id="workspace-a",
        document_id="document-a",
        document_version_id="version-a",
        logical_document_id="logical-a",
        chunk_id="chunk-a",
        content=CONTENT,
        generation_id="generation-a",
        citation_label="Moda tapusu",
    )


def _adapter(tmp_path):
    root = tmp_path / "graphrag"
    _write_native_output(root, CONTENT)
    return GraphRAGAdapter("workspace-a", root)


def test_smart_selection_chooses_artifacts_and_keeps_its_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(smart_search, "graphrag_available", lambda: True)
    monkeypatch.setattr(
        smart_search,
        "select_context",
        lambda *_args, **_kwargs: SmartSelection(("report-1",), 3, 900, 60),
    )
    adapter = _adapter(tmp_path)

    # The question shares no word with the report, so lexical selection would find nothing.
    findings = adapter.query_findings(
        GraphRoute.GLOBAL, "mülk kimde", "generation-a", sources={"chunk-a": _source()}, smart=True
    )

    assert [item.artifact_id for item in findings] == ["report-1"]
    assert adapter.last_search_usage.llm_calls == 3


def test_failed_smart_selection_falls_back_to_lexical_selection(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(smart_search, "graphrag_available", lambda: True)
    monkeypatch.setattr(smart_search, "select_context", broken)
    adapter = _adapter(tmp_path)

    findings = adapter.query_findings(
        GraphRoute.LOCAL, "Merter", "generation-a", sources={"chunk-a": _source()}, smart=True
    )

    assert [item.artifact_id for item in findings] == ["entity-1"]
    assert adapter.last_search_usage is None


def test_repeated_questions_reuse_the_selection_without_new_model_calls(tmp_path, monkeypatch):
    calls = []

    async def fake_select(*args):
        calls.append(args)
        return SmartSelection(("entity-1",), 1, 100, 10)

    monkeypatch.setattr(smart_search, "_select", fake_select)
    smart_search._cache.clear()
    settings = Settings()

    first = smart_search.select_context(tmp_path, GraphRoute.DRIFT, "Moda tapusu?", settings)
    second = smart_search.select_context(tmp_path, GraphRoute.DRIFT, "  moda   TAPUSU? ", settings)

    assert len(calls) == 1
    assert (first.llm_calls, second.llm_calls, second.cached) == (1, 0, True)
    assert second.artifact_ids == ("entity-1",)


def test_engine_reports_selection_usage_and_chat_records_it(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "graphrag_smart_search_enabled", True)
    monkeypatch.setattr(get_settings(), "graphrag_global_provider", "openai")
    monkeypatch.setattr(get_settings(), "graphrag_global_model", "gpt-4.1-mini")
    monkeypatch.setattr(smart_search, "graphrag_available", lambda: True)
    monkeypatch.setattr(
        smart_search,
        "select_context",
        lambda *_args, **_kwargs: SmartSelection(("report-1",), 2, 1_000_000, 0),
    )
    adapter = _adapter(tmp_path)
    context = SimpleNamespace(
        scope=GenerationScope("workspace-a", "generation-a", "hash"),
        trusted_sources=(_source(),),
        query_text="mülk kimde",
        step=SimpleNamespace(step_id="graphrag", engine="graphrag", capability="graphrag.global"),
    )

    output = GraphRAGProductionEngine(lambda _scope: adapter).execute(context)

    counters = output.result.trace.counters
    assert (counters["graphrag_llm_calls"], counters["validated_finding_count"]) == (2, 1)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    unused = EngineTrace(
        step_id="retrieve", engine="retrieval", capability="retrieval.x", duration_ms=1
    )
    _record_graphrag_usage(session, "workspace-a", "run", (output.result.trace, unused))
    event = session.scalars(select(UsageEvent)).one()
    assert (event.stage, event.model, event.usage_source) == (
        "graphrag_search",
        "gpt-4.1-mini",
        "estimated",
    )
    assert float(event.cost_amount) == 0.4  # 1M input tokens at $0.40/M


def test_gpt5_family_models_use_the_litellm_chat_provider():
    assert route_model_family({"model": "gpt-5.4-mini"}, "openai") == {
        "model": "gpt-5.4-mini",
        "type": "chat",
        "model_provider": "openai",
    }
    assert route_model_family({"model": "gpt-4.1-mini"}, "openai")["type"] == "openai_chat"
    local = route_model_family({"model": "gpt-5-local", "model_provider": "openai"}, "ollama")
    assert local == {"model": "gpt-5-local", "type": "openai_chat"}


def test_smart_search_is_off_by_default():
    assert Settings().graphrag_smart_search_enabled is False
    assert asyncio.iscoroutinefunction(smart_search._select)
