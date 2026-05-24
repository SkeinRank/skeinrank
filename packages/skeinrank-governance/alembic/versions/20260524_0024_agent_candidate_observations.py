"""Add agent candidate observations and evidence windows.

Revision ID: 20260524_0024
Revises: 20260524_0023
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260524_0024"
down_revision = "20260524_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_candidate_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("document_visit_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("candidate_alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("possible_canonical", sa.String(length=256), nullable=True),
        sa.Column("normalized_canonical", sa.String(length=256), nullable=True),
        sa.Column("slot", sa.String(length=64), nullable=True),
        sa.Column("observation_status", sa.String(length=32), nullable=False),
        sa.Column("discovery_score", sa.Float(), nullable=False),
        sa.Column("weighted_count", sa.Float(), nullable=False),
        sa.Column("document_frequency", sa.Integer(), nullable=False),
        sa.Column("evidence_windows_found", sa.Integer(), nullable=False),
        sa.Column("discovery_reasons_json", sa.JSON(), nullable=False),
        sa.Column("canonical_hint_json", sa.JSON(), nullable=False),
        sa.Column("candidate_pack_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "observation_status IN ('discovered', 'queued_for_review', "
            "'reviewed', 'rejected', 'needs_evidence', 'error')",
            name="agent_candidate_observation_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_visit_id"], ["agent_document_visits.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "agent_run_id",
            "normalized_alias",
            name="uq_agent_candidate_observations_run_alias",
        ),
    )
    op.create_index(
        "ix_agent_candidate_observations_run_status",
        "agent_candidate_observations",
        ["agent_run_id", "observation_status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_candidate_observations_alias",
        "agent_candidate_observations",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        "ix_agent_candidate_observations_profile_alias",
        "agent_candidate_observations",
        ["profile_id", "normalized_alias"],
        unique=False,
    )

    op.create_table(
        "agent_evidence_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("candidate_observation_id", sa.Integer(), nullable=False),
        sa.Column("document_visit_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("candidate_alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=128), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_observation_id"],
            ["agent_candidate_observations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_visit_id"], ["agent_document_visits.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["terminology_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["elasticsearch_bindings.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "candidate_observation_id",
            "evidence_hash",
            name="uq_agent_evidence_windows_candidate_hash",
        ),
    )
    op.create_index(
        "ix_agent_evidence_windows_run",
        "agent_evidence_windows",
        ["agent_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_evidence_windows_candidate",
        "agent_evidence_windows",
        ["candidate_observation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_evidence_windows_source",
        "agent_evidence_windows",
        ["source_id", "field"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_evidence_windows_source", table_name="agent_evidence_windows"
    )
    op.drop_index(
        "ix_agent_evidence_windows_candidate", table_name="agent_evidence_windows"
    )
    op.drop_index("ix_agent_evidence_windows_run", table_name="agent_evidence_windows")
    op.drop_table("agent_evidence_windows")
    op.drop_index(
        "ix_agent_candidate_observations_profile_alias",
        table_name="agent_candidate_observations",
    )
    op.drop_index(
        "ix_agent_candidate_observations_alias",
        table_name="agent_candidate_observations",
    )
    op.drop_index(
        "ix_agent_candidate_observations_run_status",
        table_name="agent_candidate_observations",
    )
    op.drop_table("agent_candidate_observations")
