"""LlamaIndex workflow definitions kept separate from durable SQLite orchestration.

The actor invokes durable checkpoints; these definitions own the in-memory handoff boundary so
Docling-normalized Markdown never leaks into API or storage adapters as a LlamaIndex detail.
"""
from llama_index.core import Document as LlamaDocument
from llama_index.core.workflow import StartEvent, StopEvent, Workflow, step


class IngestionWorkflow(Workflow):
    """Convert a persisted normalized document version into a LlamaIndex document handoff."""

    @step
    async def handoff(self, event: StartEvent) -> StopEvent:
        markdown = event.get("normalized_markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("normalized_markdown is required")
        workspace_id = event.get("workspace_id")
        version_id = event.get("document_version_id")
        if not isinstance(workspace_id, str) or not isinstance(version_id, str):
            raise ValueError("workspace_id and document_version_id are required")
        document = LlamaDocument(
            text=markdown,
            id_=version_id,
            metadata={"workspace_id": workspace_id, "document_version_id": version_id},
        )
        return StopEvent(result=document)


class ReindexWorkflow(Workflow):
    """Validate a workspace-scoped reindex request before a worker adapter executes it."""

    @step
    async def validate(self, event: StartEvent) -> StopEvent:
        workspace_id = event.get("workspace_id")
        configuration_hash = event.get("embedding_config_hash")
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ValueError("workspace_id is required")
        if not isinstance(configuration_hash, str) or not configuration_hash:
            raise ValueError("embedding_config_hash is required")
        return StopEvent(
            result={"workspace_id": workspace_id, "embedding_config_hash": configuration_hash}
        )
