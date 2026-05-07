"""Add Elasticsearch enrichment bindings.

Revision ID: 20260507_0006
Revises: 20260507_0005
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260507_0006"
down_revision = "20260507_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "elasticsearch_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            server_default="elasticsearch",
        ),
        sa.Column("index_name", sa.String(length=256), nullable=False),
        sa.Column("text_fields", sa.JSON(), nullable=False),
        sa.Column("target_field", sa.String(length=256), nullable=False),
        sa.Column("filter_field", sa.String(length=256), nullable=True),
        sa.Column("filter_value", sa.String(length=512), nullable=True),
        sa.Column(
            "mode", sa.String(length=32), nullable=False, server_default="dry_run"
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('elasticsearch')",
            name=op.f("ck_elasticsearch_bindings_elasticsearch_binding_provider"),
        ),
        sa.CheckConstraint(
            "mode IN ('dry_run', 'write')",
            name=op.f("ck_elasticsearch_bindings_elasticsearch_binding_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["terminology_profiles.id"],
            name=op.f("fk_elasticsearch_bindings_profile_id_terminology_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_elasticsearch_bindings")),
        sa.UniqueConstraint(
            "normalized_name",
            name="uq_elasticsearch_bindings_normalized_name",
        ),
    )
    op.create_index(
        "ix_elasticsearch_bindings_profile_enabled",
        "elasticsearch_bindings",
        ["profile_id", "is_enabled"],
        unique=False,
    )
    op.create_index(
        "ix_elasticsearch_bindings_index",
        "elasticsearch_bindings",
        ["index_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_elasticsearch_bindings_index", table_name="elasticsearch_bindings"
    )
    op.drop_index(
        "ix_elasticsearch_bindings_profile_enabled",
        table_name="elasticsearch_bindings",
    )
    op.drop_table("elasticsearch_bindings")
