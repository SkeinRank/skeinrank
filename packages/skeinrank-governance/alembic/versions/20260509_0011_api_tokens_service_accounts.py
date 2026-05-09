"""Add API tokens and service accounts.

Revision ID: 20260509_0011
Revises: 20260509_0010
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0011"
down_revision = "20260509_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_service_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'moderator', 'contributor')",
            name=op.f("ck_governance_service_accounts_governance_service_account_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_service_accounts")),
        sa.UniqueConstraint("name", name=op.f("uq_governance_service_accounts_name")),
        sa.UniqueConstraint(
            "normalized_name",
            name=op.f("uq_governance_service_accounts_normalized_name"),
        ),
    )
    op.create_index(
        "ix_governance_service_accounts_normalized_name",
        "governance_service_accounts",
        ["normalized_name"],
        unique=False,
    )

    op.create_table(
        "governance_api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("service_account_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND service_account_id IS NULL) OR "
            "(user_id IS NULL AND service_account_id IS NOT NULL)",
            name=op.f("ck_governance_api_tokens_governance_api_token_single_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["service_account_id"],
            ["governance_service_accounts.id"],
            name=op.f(
                "fk_governance_api_tokens_service_account_id_governance_service_accounts"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["governance_users.id"],
            name=op.f("fk_governance_api_tokens_user_id_governance_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_governance_api_tokens")),
        sa.UniqueConstraint(
            "token_hash", name=op.f("uq_governance_api_tokens_token_hash")
        ),
    )
    op.create_index(
        "ix_governance_api_tokens_service_account_created",
        "governance_api_tokens",
        ["service_account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_governance_api_tokens_user_created",
        "governance_api_tokens",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_governance_api_tokens_user_created",
        table_name="governance_api_tokens",
    )
    op.drop_index(
        "ix_governance_api_tokens_service_account_created",
        table_name="governance_api_tokens",
    )
    op.drop_table("governance_api_tokens")
    op.drop_index(
        "ix_governance_service_accounts_normalized_name",
        table_name="governance_service_accounts",
    )
    op.drop_table("governance_service_accounts")
