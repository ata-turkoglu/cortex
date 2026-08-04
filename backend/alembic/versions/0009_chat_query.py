"""add workspace-scoped conversations and query diagnostics

Revision ID: 0009_chat_query
Revises: 0008_workflow_locks
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_chat_query"
down_revision = "0008_workflow_locks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("summary", sa.Text()))
    op.create_index(
        "ix_conversations_workspace_updated", "conversations", ["workspace_id", "updated_at"]
    )
    # SQLite cannot add a foreign-key constraint through ALTER TABLE; the application
    # enforces the workspace-scoped query-run relationship and fresh installs retain it
    # through the ORM schema.
    op.add_column("messages", sa.Column("query_run_id", sa.String(36)))
    op.add_column(
        "messages", sa.Column("status", sa.String(32), nullable=False, server_default="completed")
    )
    op.add_column("messages", sa.Column("citations_json", sa.Text()))
    op.add_column("messages", sa.Column("metadata_json", sa.Text()))
    op.add_column("messages", sa.Column("edited_at", sa.DateTime()))
    op.add_column("messages", sa.Column("updated_at", sa.DateTime()))
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    for name, type_, nullable, default in (
        ("selected_routes_json", sa.Text(), True, None),
        ("route_reason", sa.Text(), True, None),
        ("route_confidence", sa.Float(), True, None),
        ("answer_state", sa.String(32), True, None),
        ("latency_ms", sa.Integer(), True, None),
        ("input_tokens", sa.Integer(), False, "0"),
        ("output_tokens", sa.Integer(), False, "0"),
        ("estimated_cost_usd", sa.Float(), False, "0"),
    ):
        op.add_column(
            "query_runs", sa.Column(name, type_, nullable=nullable, server_default=default)
        )


def downgrade():
    raise NotImplementedError(
        "Downgrade is intentionally unsupported for this data-bearing migration"
    )
