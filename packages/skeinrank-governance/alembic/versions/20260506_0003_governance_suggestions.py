"""Add governance suggestions.

Revision ID: 20260506_0003
Revises: 20260505_0002
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260506_0003"
down_revision = "20260505_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("alias_id", sa.Integer(), nullable=True),
        sa.Column("canonical_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=False),
        sa.Column("alias_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_governance_suggestions_governance_suggestion_status"),
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'discovery', 'import')",
            name=op.f("ck_governance_suggestions_governance_suggestion_source"),
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name=op.f(
                "ck_governance_suggestions_governance_suggestion_confidence_range"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["alias_id"],
            ["term_aliases.id"],
            name=op.f("fk_governance_suggestions_alias_id_term_aliases"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_governance_suggestions_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_suggestions")),
    )
    op.create_index(
        "ix_governance_suggestions_profile_alias",
        "governance_suggestions",
        ["profile_id", "normalized_alias"],
        unique=False,
    )
    op.create_index(
        "ix_governance_suggestions_profile_status",
        "governance_suggestions",
        ["profile_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_suggestions_profile_status",
        table_name="governance_suggestions",
    )
    op.drop_index(
        "ix_governance_suggestions_profile_alias",
        table_name="governance_suggestions",
    )
    op.drop_table("governance_suggestions")
