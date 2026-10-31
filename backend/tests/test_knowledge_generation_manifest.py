import json

from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.production_executor import ProductionKnowledgeExecutor


def test_candidate_source_manifest_is_immutable_generation_authority(tmp_path):
    executor = ProductionKnowledgeExecutor.__new__(ProductionKnowledgeExecutor)
    executor.root = tmp_path / "workspaces" / "workspace-a" / "knowledge-candidates"
    executor.workspace_id = "workspace-a"
    executor.data_root = tmp_path
    snapshot = CorpusSnapshot(
        "workspace-a",
        "source-fingerprint",
        (
            SourceChunk(
                "chunk-a",
                "document-a",
                "version-a",
                "logical-a",
                0,
                "Ada is a historian.",
                "content-hash-a",
            ),
        ),
    )

    identity = executor._write_source_manifest(snapshot, "generation-a")
    path = tmp_path / identity.uri

    record = json.loads(path.read_text(encoding="utf-8"))
    assert path.as_posix().endswith("knowledge-candidates/generation-a/source/manifest.jsonl")
    assert record["chunk_id"] == "chunk-a"
    assert record["chunk_index"] == 0
    assert identity.sha256
