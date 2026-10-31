"""persist scope-aware rejected countable assertion blockers

Revision ID: 0027_rejected_assertion_blockers
Revises: 0026_query_run_completeness
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_rejected_assertion_blockers"
down_revision = "0026_query_run_completeness"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rejected_assertion_blockers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("blocker_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=True),
        sa.Column("potentially_countable", sa.Boolean(), nullable=False),
        sa.Column("affected_dimension", sa.String(length=64), nullable=True),
        sa.Column("normalized_subject_surname", sa.String(length=255), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("logical_document_id", sa.String(length=72), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope_hints_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["knowledge_generations.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "generation_id", "chunk_id", "span_start", "span_end", "reason"
        ),
    )
    op.create_index(
        "ix_rejected_assertion_blockers_scope",
        "rejected_assertion_blockers",
        ["workspace_id", "generation_id", "normalized_subject_surname"],
    )


def downgrade():
    op.drop_index("ix_rejected_assertion_blockers_scope", table_name="rejected_assertion_blockers")
    op.drop_table("rejected_assertion_blockers")
