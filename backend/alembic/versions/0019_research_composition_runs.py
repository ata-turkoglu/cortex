"""add durable Query V2 research and composition runs

Revision ID: 0019_research_composition_runs
Revises: 0018_conversation_contexts
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_research_composition_runs"
down_revision = "0018_conversation_contexts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("generation_id", sa.String(length=128), nullable=True),
        sa.Column("checkpoint_json", sa.Text(), nullable=False),
        sa.Column("failure_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_runs_workspace_updated", "research_runs", ["workspace_id", "updated_at"]
    )
    op.create_table(
        "composition_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("research_run_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("checkpoint_json", sa.Text(), nullable=False),
        sa.Column("failure_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_composition_runs_workspace_updated",
        "composition_runs",
        ["workspace_id", "updated_at"],
    )


def downgrade():
    op.drop_index("ix_composition_runs_workspace_updated", table_name="composition_runs")
    op.drop_table("composition_runs")
    op.drop_index("ix_research_runs_workspace_updated", table_name="research_runs")
    op.drop_table("research_runs")
