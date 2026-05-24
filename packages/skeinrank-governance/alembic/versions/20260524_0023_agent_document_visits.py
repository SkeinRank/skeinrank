"""Add agent document visits.

Revision ID: 20260524_0023
Revises: 20260524_0022
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260524_0023"
down_revision = "20260524_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_document_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.String(length=512), nullable=False),
        sa.Column("external_document_id", sa.String(length=512), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("index_name", sa.String(length=256), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("processing_context_hash", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("openrouter_model", sa.String(length=128), nullable=True),
        sa.Column("visit_status", sa.String(length=32), nullable=False),
        sa.Column("should_scan", sa.Boolean(), nullable=False),
        sa.Column("evidence_windows_found", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visit_status IN ('new_document', 'unchanged_seen', 'content_changed', "
            "'context_changed', 'skipped', 'error')",
            name="agent_document_visit_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "agent_run_id",
            "source_id",
            name="uq_agent_document_visits_run_source",
        ),
    )
    op.create_index(
        "ix_agent_document_visits_run_status",
        "agent_document_visits",
        ["agent_run_id", "visit_status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_document_visits_source_created",
        "agent_document_visits",
        ["source_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_document_visits_binding_source",
        "agent_document_visits",
        ["binding_id", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_document_visits_hashes",
        "agent_document_visits",
        ["content_hash", "processing_context_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_document_visits_hashes", table_name="agent_document_visits")
    op.drop_index(
        "ix_agent_document_visits_binding_source", table_name="agent_document_visits"
    )
    op.drop_index(
        "ix_agent_document_visits_source_created", table_name="agent_document_visits"
    )
    op.drop_index(
        "ix_agent_document_visits_run_status", table_name="agent_document_visits"
    )
    op.drop_table("agent_document_visits")
