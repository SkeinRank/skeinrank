"""Add Elasticsearch enrichment write strategy.

Revision ID: 20260508_0007
Revises: 20260507_0006
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_0007"
down_revision = "20260507_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "elasticsearch_bindings",
        sa.Column(
            "write_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="reindex_alias_swap",
        ),
    )


def downgrade() -> None:
    op.drop_column("elasticsearch_bindings", "write_strategy")
