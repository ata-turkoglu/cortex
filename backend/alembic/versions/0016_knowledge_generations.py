"""add atomic knowledge generation readiness

Revision ID: 0016_knowledge_generations
Revises: 0015_usage_pricing_snapshot
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_knowledge_generations"
down_revision = "0015_usage_pricing_snapshot"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("failure_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_generation_workspace_state",
        "knowledge_generations",
        ["workspace_id", "state"],
    )
    op.create_table(
        "knowledge_stage_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("output_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["knowledge_generations.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_id", "stage"),
    )


def downgrade():
    op.drop_table("knowledge_stage_states")
    op.drop_index(
        "ix_knowledge_generation_workspace_state", table_name="knowledge_generations"
    )
    op.drop_table("knowledge_generations")
