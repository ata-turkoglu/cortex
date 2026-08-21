"""preserve applied pricing snapshots on usage events

Revision ID: 0015_usage_pricing_snapshot
Revises: 0014_usage_events
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_usage_pricing_snapshot"
down_revision = "0014_usage_events"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usage_events") as batch:
        batch.add_column(sa.Column("pricing_snapshot_json", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("usage_events") as batch:
        batch.drop_column("pricing_snapshot_json")
