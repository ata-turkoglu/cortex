"""persist governed surname on canonical generation membership

Revision ID: 0023_canonical_membership_surname
Revises: 0022_minimal_canonical_core
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_canonical_membership_surname"
down_revision = "0022_minimal_canonical_core"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("generation_canonical_memberships") as batch:
        batch.add_column(sa.Column("surname", sa.String(255)))
        batch.add_column(sa.Column("normalized_surname", sa.String(255)))
        batch.add_column(sa.Column("surname_mention_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_generation_membership_surname_mention",
            "entity_mentions",
            ["surname_mention_id"],
            ["id"],
        )
        batch.create_index(
            "ix_generation_membership_surname",
            ["workspace_id", "generation_id", "normalized_surname"],
        )


def downgrade():
    with op.batch_alter_table("generation_canonical_memberships") as batch:
        batch.drop_index("ix_generation_membership_surname")
        batch.drop_constraint("fk_generation_membership_surname_mention", type_="foreignkey")
        batch.drop_column("surname_mention_id")
        batch.drop_column("normalized_surname")
        batch.drop_column("surname")
