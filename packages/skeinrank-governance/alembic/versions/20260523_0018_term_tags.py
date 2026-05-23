"""Add canonical term tags.

Revision ID: 20260523_0018
Revises: 20260523_0017
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0018"
down_revision = "20260523_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "term_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("normalized_value", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["term_id"], ["canonical_terms.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "term_id",
            "normalized_value",
            name="uq_term_tags_term_normalized_value",
        ),
    )
    op.create_index(
        "ix_term_tags_normalized_value",
        "term_tags",
        ["normalized_value"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_term_tags_normalized_value", table_name="term_tags")
    op.drop_table("term_tags")
