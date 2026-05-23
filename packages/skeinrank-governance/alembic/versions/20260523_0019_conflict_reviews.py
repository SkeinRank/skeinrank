"""Add governance conflict review state.

Revision ID: 20260523_0019
Revises: 20260523_0018
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260523_0019"
down_revision = "20260523_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_conflict_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("conflict_type", sa.String(length=128), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="governance_conflict_review_severity",
        ),
        sa.CheckConstraint(
            "review_status IN ('open', 'ignored', 'resolved')",
            name="governance_conflict_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "fingerprint",
            name="uq_governance_conflict_reviews_fingerprint",
        ),
    )
    op.create_index(
        "ix_governance_conflict_reviews_profile_status",
        "governance_conflict_reviews",
        ["profile_id", "review_status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_conflict_reviews_type_severity",
        "governance_conflict_reviews",
        ["conflict_type", "severity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_conflict_reviews_type_severity",
        table_name="governance_conflict_reviews",
    )
    op.drop_index(
        "ix_governance_conflict_reviews_profile_status",
        table_name="governance_conflict_reviews",
    )
    op.drop_table("governance_conflict_reviews")
