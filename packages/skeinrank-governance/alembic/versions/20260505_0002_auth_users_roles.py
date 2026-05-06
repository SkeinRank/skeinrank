"""Add governance users and auth tokens.

Revision ID: 20260505_0002
Revises: 20260503_0001
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260505_0002"
down_revision = "20260503_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("normalized_username", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'moderator', 'contributor')",
            name=op.f("ck_governance_users_governance_user_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_users")),
        sa.UniqueConstraint("username", name=op.f("uq_governance_users_username")),
        sa.UniqueConstraint(
            "normalized_username",
            name=op.f("uq_governance_users_normalized_username"),
        ),
    )
    op.create_index(
        "ix_governance_users_normalized_username",
        "governance_users",
        ["normalized_username"],
        unique=False,
    )
    op.create_table(
        "governance_auth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["governance_users.id"],
            name=op.f("fk_governance_auth_tokens_user_id_governance_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_auth_tokens")),
        sa.UniqueConstraint(
            "token_hash", name=op.f("uq_governance_auth_tokens_token_hash")
        ),
    )
    op.create_index(
        "ix_governance_auth_tokens_user_created",
        "governance_auth_tokens",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_auth_tokens_user_created",
        table_name="governance_auth_tokens",
    )
    op.drop_table("governance_auth_tokens")
    op.drop_index(
        "ix_governance_users_normalized_username",
        table_name="governance_users",
    )
    op.drop_table("governance_users")
