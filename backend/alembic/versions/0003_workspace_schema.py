"""add workspace-scoped relational schema

Revision ID: 0003_workspace_schema
Revises: 0002_usage_records
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_workspace_schema"
down_revision = "0002_usage_records"
branch_labels = None
depends_on = None


def table(name, *columns, **kw):
    op.create_table(name, sa.Column("id", sa.String(36), primary_key=True), *columns, **kw)


def scope():
    return sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False)


def upgrade():
    table(
        "workspaces",
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
    )
    table(
        "workspace_resources",
        scope(),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("logical_name", sa.String(128), nullable=False),
        sa.Column("backend_name", sa.String(255)),
        sa.Column("path", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("workspace_id", "resource_type", "logical_name"),
    )
    op.create_index(
        "ix_workspace_resources_workspace_type",
        "workspace_resources",
        ["workspace_id", "resource_type"],
    )
    table(
        "folders",
        scope(),
        sa.Column("parent_id", sa.String(36)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
    )
    table(
        "documents",
        scope(),
        sa.Column("folder_id", sa.String(36)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("active_version_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
    )
    op.create_index("ix_documents_workspace_created", "documents", ["workspace_id", "created_at"])
    op.create_index("ix_documents_workspace_hash", "documents", ["workspace_id", "content_hash"])
    table(
        "document_versions",
        scope(),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("source_hash", sa.String(128), nullable=False),
        sa.Column("normalized_content_hash", sa.String(128)),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("normalized_path", sa.Text),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
        sa.UniqueConstraint("document_id", "version_number"),
        sa.UniqueConstraint("workspace_id", "source_hash"),
    )
    table(
        "chunks",
        scope(),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
        sa.UniqueConstraint("document_version_id", "ordinal"),
    )
    table(
        "chunk_relationships",
        scope(),
        sa.Column("source_chunk_id", sa.String(36), nullable=False),
        sa.Column("target_chunk_id", sa.String(36), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
    )
    table(
        "conversations",
        scope(),
        sa.Column("title", sa.String(512)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
    )
    table(
        "messages",
        scope(),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    table(
        "message_citations",
        scope(),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36)),
        sa.Column("chunk_id", sa.String(36)),
        sa.Column("evidence_json", sa.Text, nullable=False),
    )
    table(
        "workflow_definitions",
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("definition_json", sa.Text, nullable=False),
    )
    table(
        "workflow_runs",
        scope(),
        sa.Column("definition_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("recovery_state", sa.String(32)),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("deleted_at", sa.DateTime),
    )
    table(
        "workflow_step_runs",
        scope(),
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False),
        sa.Column("checkpoint_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    table(
        "workflow_events",
        scope(),
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    table(
        "query_runs",
        scope(),
        sa.Column("conversation_id", sa.String(36)),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    table(
        "query_step_runs",
        scope(),
        sa.Column("query_run_id", sa.String(36), nullable=False),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "global_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "provider_connections",
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("validation_json", sa.Text),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "model_assignments",
        sa.Column("layer", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "setup_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("state_json", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "workspace_index_states",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("dense_state", sa.String(32), nullable=False),
        sa.Column("sparse_state", sa.String(32), nullable=False),
        sa.Column("embedding_config_hash", sa.String(128)),
        sa.Column("indexed_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "graphrag_states",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("pending_document_count", sa.Integer, nullable=False),
        sa.Column("graph_root", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.add_column("usage_records", sa.Column("workspace_id", sa.String(36)))
    op.create_index(
        "ix_usage_records_workspace_created", "usage_records", ["workspace_id", "created_at"]
    )


def downgrade():
    raise NotImplementedError(
        "Downgrade is intentionally unsupported for this data-bearing migration"
    )
