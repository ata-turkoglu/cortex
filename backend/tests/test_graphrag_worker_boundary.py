from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKER_DEPENDENCY_SYNC = (
    "uv sync --frozen --no-dev --group query --group retrieval --group graphrag --no-editable"
)


def test_api_chat_does_not_import_graphrag_execution_runtime():
    api_chat = (BACKEND_ROOT / "app" / "api" / "chat.py").read_text(encoding="utf-8")
    chat_service = (BACKEND_ROOT / "app" / "chat" / "service.py").read_text(encoding="utf-8")

    assert "graphrag.adapter" not in api_chat
    assert "graphrag.adapter" not in chat_service
    assert "GraphRAGAdapter" not in chat_service


def test_worker_image_is_the_only_graphrag_dependency_target():
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM query-deps AS backend-builder" in dockerfile
    assert "uv sync --frozen --no-dev --group query --no-editable" in dockerfile
    assert WORKER_DEPENDENCY_SYNC in dockerfile
