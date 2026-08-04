"""add GraphRAG stage usage reports

Revision ID: 0007_graphrag_stage_reports
Revises: 0006_retrieval_embedding_state
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_graphrag_stage_reports"
down_revision = "0006_retrieval_embedding_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "graphrag_stage_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("estimated_cost_usd", sa.Float, nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_graphrag_stage_reports_workspace_stage",
        "graphrag_stage_reports",
        ["workspace_id", "stage"],
    )


def downgrade():
    op.drop_index("ix_graphrag_stage_reports_workspace_stage", "graphrag_stage_reports")
    op.drop_table("graphrag_stage_reports")
