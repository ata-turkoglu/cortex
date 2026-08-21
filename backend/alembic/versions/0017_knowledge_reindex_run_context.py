"""persist knowledge reindex run context

Revision ID: 0017_knowledge_reindex_run_context
Revises: 0016_knowledge_generations
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_knowledge_reindex_run_context"
down_revision = "0016_knowledge_generations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_reindex_run_contexts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"]),
        sa.ForeignKeyConstraint(["generation_id"], ["knowledge_generations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id"),
    )


def downgrade():
    op.drop_table("knowledge_reindex_run_contexts")
