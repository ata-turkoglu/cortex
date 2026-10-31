from types import SimpleNamespace

from app.query.service import _has_structured_result, _retrieval_query
from app.query.understanding import SemanticEntity, SemanticUnderstanding


def _plan(*steps):
    return SimpleNamespace(graph=SimpleNamespace(steps=steps))


def _step(step_id, engine, node_id, dependencies=()):
    return SimpleNamespace(
        step_id=step_id,
        engine=engine,
        dependencies=dependencies,
        trace=SimpleNamespace(logical_node_ids=(node_id,)),
    )


def test_query_completeness_applies_only_to_final_structured_results():
    ir = SimpleNamespace(root_ids=("root",))
    retrieval = _plan(_step("retrieve", "retrieval", "root"))
    structured = _plan(
        _step("count", "structured", "count"),
        _step("answer", "result_evidence", "root", dependencies=("count",)),
    )

    assert _has_structured_result(retrieval, ir) is False
    assert _has_structured_result(structured, ir) is True
    assert _has_structured_result(SimpleNamespace(graph=None), ir) is False


def test_follow_up_referents_are_visible_to_retrieval_text():
    understanding = SemanticUnderstanding(
        state="resolved",
        confidence=0.9,
        entities=(
            SemanticEntity(
                reference_id="person-1",
                mention="onun",
                entity_type="person",
                reference_kind="follow_up",
                resolution="resolved",
                canonical_entity_id="entity-1",
                display_name="Ali Merter",
            ),
        ),
    )

    assert _retrieval_query("Peki onun mülkleri?", understanding) == (
        "Peki onun mülkleri? Ali Merter"
    )
    assert _retrieval_query("Ali Merter kimdir?", understanding) == "Ali Merter kimdir?"


def test_chat_endpoint_runs_off_the_server_event_loop():
    """V2 mixes awaits with blocking SQLite/Qdrant/BM25 work; it must use the threadpool."""
    import inspect

    from app.api.chat import query

    assert not inspect.iscoroutinefunction(query)


def test_v2_retrieval_reads_the_configured_dense_bm25_and_fusion_limits(monkeypatch):
    from app.core.config import get_settings
    from app.query.service import V2QueryService

    captured = {}

    class RecordingExecutor:
        def __init__(self, *args):
            pass

        def execute_plan(self, *args, **kwargs):
            captured.update(kwargs)
            return "executed"

    monkeypatch.setattr("app.query.service.V2PlanExecutor", RecordingExecutor)
    monkeypatch.setattr(get_settings(), "dense_top_k", 12)
    monkeypatch.setattr(get_settings(), "bm25_top_k", 7)
    monkeypatch.setattr(get_settings(), "fusion_candidate_limit", 9)
    service = V2QueryService.__new__(V2QueryService)
    service.executor = SimpleNamespace(dense=None, sparse=None, registry=None)
    prepared = SimpleNamespace(physical_plan=None, logical_ir=SimpleNamespace(nodes=()))

    assert service._execute_bound(prepared, None, [0.0], "soru", ()) == "executed"
    assert (
        captured["dense_limit"],
        captured["sparse_limit"],
        captured["fusion_limit"],
    ) == (12, 7, 9)
