import asyncio

from app.workflows.llamaindex import IngestionWorkflow, ReindexWorkflow


async def run_ingestion():
    return await IngestionWorkflow().run(
        normalized_markdown="# Merhaba", workspace_id="workspace-a", document_version_id="version-a"
    )


def test_ingestion_workflow_hands_normalized_markdown_to_llamaindex():
    result = asyncio.run(run_ingestion())
    assert result.id_ == "version-a"
    assert result.metadata["workspace_id"] == "workspace-a"


async def run_reindex():
    return await ReindexWorkflow().run(
        workspace_id="workspace-a", embedding_config_hash="config-a"
    )


def test_reindex_workflow_requires_workspace_scoped_configuration():
    result = asyncio.run(run_reindex())
    assert result["embedding_config_hash"] == "config-a"
