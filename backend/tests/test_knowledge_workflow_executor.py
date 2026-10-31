import pytest

from app.knowledge.pipeline import CorpusSnapshot, StageResult
from app.knowledge.workflow_executor import KnowledgeWorkflowExecutor


def test_routes_only_explicit_generation_bound_stage_handlers():
    snapshot = CorpusSnapshot("workspace", "source", ())
    executor = KnowledgeWorkflowExecutor(
        {
            "bm25": lambda current, generation: StageResult(
                generation, current.fingerprint, "bm25:output", {}
            )
        }
    )
    assert executor.execute("bm25", snapshot, "candidate").output_fingerprint == "bm25:output"
    with pytest.raises(RuntimeError, match="not configured"):
        executor.execute("graphrag", snapshot, "candidate")


def test_rejects_mismatched_adapter_result():
    executor = KnowledgeWorkflowExecutor(
        {"bm25": lambda current, generation: StageResult("other", current.fingerprint, "out", {})}
    )
    with pytest.raises(ValueError, match="mismatched"):
        executor.execute("bm25", CorpusSnapshot("workspace", "source", ()), "candidate")
