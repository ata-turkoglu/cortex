"""normalized immutable provider usage events

Revision ID: 0014_usage_events
Revises: 0013_bm25_workspace_resource
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_usage_events"
down_revision = "0013_bm25_workspace_resource"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("query_run_id", sa.String(36), sa.ForeignKey("query_runs.id")),
        sa.Column("workflow_run_id", sa.String(36), sa.ForeignKey("workflow_runs.id")),
        sa.Column("workflow_step_id", sa.String(36), sa.ForeignKey("workflow_step_runs.id")),
        sa.Column("stage", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()), sa.Column("cached_input_tokens", sa.Integer()),
        sa.Column("cache_creation_tokens", sa.Integer()), sa.Column("reasoning_tokens", sa.Integer()),
        sa.Column("embedding_tokens", sa.Integer()), sa.Column("usage_source", sa.String(32), nullable=False),
        sa.Column("cost_status", sa.String(32), nullable=False), sa.Column("cost_amount", sa.Numeric(20, 10)),
        sa.Column("currency", sa.String(8)), sa.Column("pricing_version", sa.String(128)),
        sa.Column("diagnostic", sa.String(255)), sa.Column("provider_usage_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_usage_events_workspace_query", "usage_events", ["workspace_id", "query_run_id"])
    op.create_index("ix_usage_events_workspace_workflow", "usage_events", ["workspace_id", "workflow_run_id"])


def downgrade():
    op.drop_table("usage_events")
