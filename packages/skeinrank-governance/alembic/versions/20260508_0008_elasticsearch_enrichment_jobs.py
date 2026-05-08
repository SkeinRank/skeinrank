"""Add Elasticsearch enrichment jobs.

Revision ID: 20260508_0008
Revises: 20260508_0007
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_0008"
down_revision = "20260508_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "elasticsearch_enrichment_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("binding_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="queued"
        ),
        sa.Column("write_strategy", sa.String(length=32), nullable=False),
        sa.Column("source_index", sa.String(length=256), nullable=False),
        sa.Column("target_index", sa.String(length=256), nullable=True),
        sa.Column("alias_name", sa.String(length=256), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("documents_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "documents_enriched", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("documents_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="elasticsearch_enrichment_job_status",
        ),
        sa.CheckConstraint(
            "write_strategy IN ('in_place', 'reindex_alias_swap')",
            name="elasticsearch_enrichment_job_write_strategy",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_elasticsearch_enrichment_jobs_binding_created",
        "elasticsearch_enrichment_jobs",
        ["binding_id", "created_at"],
    )
    op.create_index(
        "ix_elasticsearch_enrichment_jobs_status",
        "elasticsearch_enrichment_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_elasticsearch_enrichment_jobs_status",
        table_name="elasticsearch_enrichment_jobs",
    )
    op.drop_index(
        "ix_elasticsearch_enrichment_jobs_binding_created",
        table_name="elasticsearch_enrichment_jobs",
    )
    op.drop_table("elasticsearch_enrichment_jobs")
