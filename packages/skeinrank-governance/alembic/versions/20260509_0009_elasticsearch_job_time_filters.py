"""Add Elasticsearch enrichment job time filters.

Revision ID: 20260509_0009
Revises: 20260508_0008
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0009"
down_revision = "20260508_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "elasticsearch_bindings",
        sa.Column("timestamp_field", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "elasticsearch_bindings",
        sa.Column("time_window_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("elasticsearch_bindings", "time_window_days")
    op.drop_column("elasticsearch_bindings", "timestamp_field")
