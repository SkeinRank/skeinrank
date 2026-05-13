"""Add snapshot-aware binding runtime state.

Revision ID: 20260509_0015
Revises: 20260509_0014
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0015"
down_revision = "20260509_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("elasticsearch_bindings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_successful_snapshot_version", sa.String(length=128), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_successful_snapshot_at", sa.DateTime(timezone=True), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("last_successful_job_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pending_snapshot_version", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("runtime_snapshot_json", sa.JSON(), nullable=True)
        )
    op.create_index(
        "ix_elasticsearch_bindings_snapshot_version",
        "elasticsearch_bindings",
        ["profile_id", "last_successful_snapshot_version"],
        unique=False,
    )

    with op.batch_alter_table("elasticsearch_enrichment_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("snapshot_version", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(sa.Column("snapshot_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("previous_snapshot_version", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("previous_snapshot_json", sa.JSON(), nullable=True)
        )
    op.create_index(
        "ix_elasticsearch_enrichment_jobs_snapshot_version",
        "elasticsearch_enrichment_jobs",
        ["profile_id", "snapshot_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_elasticsearch_enrichment_jobs_snapshot_version",
        table_name="elasticsearch_enrichment_jobs",
    )
    with op.batch_alter_table("elasticsearch_enrichment_jobs") as batch_op:
        batch_op.drop_column("previous_snapshot_json")
        batch_op.drop_column("previous_snapshot_version")
        batch_op.drop_column("snapshot_json")
        batch_op.drop_column("snapshot_version")

    op.drop_index(
        "ix_elasticsearch_bindings_snapshot_version",
        table_name="elasticsearch_bindings",
    )
    with op.batch_alter_table("elasticsearch_bindings") as batch_op:
        batch_op.drop_column("runtime_snapshot_json")
        batch_op.drop_column("pending_snapshot_version")
        batch_op.drop_column("last_successful_job_id")
        batch_op.drop_column("last_successful_snapshot_at")
        batch_op.drop_column("last_successful_snapshot_version")
