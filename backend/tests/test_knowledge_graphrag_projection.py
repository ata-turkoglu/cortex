import pytest

from app.knowledge.graphrag_projection import (
    GenerationBoundGraphRAGProjection,
    GraphRAGProjectionSummary,
)
from app.knowledge.pipeline import CorpusSnapshot


def test_graph_projection_requires_candidate_generation_match():
    snapshot = CorpusSnapshot("workspace", "source", ())
    adapter = GenerationBoundGraphRAGProjection(
        lambda workspace, generation: GraphRAGProjectionSummary(
            workspace, generation, 3, 2
        )
    )
    result = adapter.build_for_generation(snapshot, "candidate")
    assert result.output_fingerprint.startswith("graphrag:")
    mismatched = GenerationBoundGraphRAGProjection(
        lambda workspace, generation: GraphRAGProjectionSummary(workspace, "other", 3, 2)
    )
    with pytest.raises(ValueError, match="different generation"):
        mismatched.build_for_generation(snapshot, "candidate")
