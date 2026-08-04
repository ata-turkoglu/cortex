"""add workspace workflow locks

Revision ID: 0008_workflow_locks
Revises: 0007_graphrag_stage_reports
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_workflow_locks"
down_revision = "0007_graphrag_stage_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_locks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("lock_type", sa.String(64), nullable=False),
        sa.Column(
            "workflow_run_id", sa.String(36), sa.ForeignKey("workflow_runs.id"), nullable=False
        ),
        sa.Column("acquired_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("workspace_id", "lock_type"),
    )
    op.create_index("ix_workflow_runs_workspace_state", "workflow_runs", ["workspace_id", "state"])
    op.create_index(
        "ix_workflow_steps_run", "workflow_step_runs", ["workflow_run_id", "created_at"]
    )
    op.create_index("ix_workflow_events_run", "workflow_events", ["workflow_run_id", "created_at"])


def downgrade():
    raise NotImplementedError(
        "Downgrade is intentionally unsupported for this data-bearing migration"
    )
