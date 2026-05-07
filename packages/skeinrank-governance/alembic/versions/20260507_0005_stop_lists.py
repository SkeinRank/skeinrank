"""Add profile stop lists.

Revision ID: 20260507_0005
Revises: 20260507_0004
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260507_0005"
down_revision = "20260507_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_stop_list_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column(
            "target", sa.String(length=32), nullable=False, server_default="both"
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target IN ('alias', 'canonical', 'both')",
            name=op.f("ck_governance_stop_list_entries_governance_stop_list_target"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f(
                "fk_governance_stop_list_entries_profile_id_terminology_profiles"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_stop_list_entries")),
        sa.UniqueConstraint(
            "profile_id",
            "target",
            "normalized_value",
            name="uq_governance_stop_list_profile_target_value",
        ),
    )
    op.create_index(
        "ix_governance_stop_list_profile_target_active",
        "governance_stop_list_entries",
        ["profile_id", "target", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_stop_list_profile_target_active",
        table_name="governance_stop_list_entries",
    )
    op.drop_table("governance_stop_list_entries")
