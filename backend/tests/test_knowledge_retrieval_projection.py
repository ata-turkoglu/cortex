from app.knowledge.pipeline import CorpusSnapshot
from app.knowledge.retrieval_projection import WorkspaceRetrievalProjection
from app.retrieval.indexing import IndexingSummary


def test_rebuilds_bm25_and_dense_once_per_generation_and_binds_fingerprint():
    calls = []

    def rebuild(workspace_id):
        calls.append(workspace_id)
        return IndexingSummary(workspace_id, 4, "embedding-config")

    projection = WorkspaceRetrievalProjection(rebuild)
    snapshot = CorpusSnapshot("workspace-a", "source-fingerprint", ())
    first = projection.build(snapshot, "generation-a")
    second = projection.build(snapshot, "generation-a")
    assert calls == ["workspace-a"]
    assert first == second
    assert first.bm25.input_fingerprint == "source-fingerprint"
    assert first.dense_qdrant.output_fingerprint.startswith("dense_qdrant:")
