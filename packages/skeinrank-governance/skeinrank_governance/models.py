"""SQLAlchemy models for SkeinRank terminology governance.

The database is a control plane for terminology editing and snapshot publishing.
Hot-path extraction should continue to load an exported snapshot and build an
in-memory matcher.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ACTIVE_STATUS = "active"
TERM_STATUSES = ("active", "deprecated", "disabled")
ALIAS_STATUSES = (
    "active",
    "deprecated",
    "disabled",
    "ambiguous",
    "pending",
    "rejected",
)
SNAPSHOT_STATUSES = ("draft", "published", "archived")
SUGGESTION_STATUSES = ("pending", "approved", "rejected")
SUGGESTION_TYPES = ("alias", "canonical_term")
SUGGESTION_SOURCES = ("manual", "discovery", "import")
STOP_LIST_TARGETS = ("alias", "canonical", "both")
ELASTICSEARCH_BINDING_MODES = ("dry_run", "write")
ELASTICSEARCH_BINDING_WRITE_STRATEGIES = ("in_place", "reindex_alias_swap")
ELASTICSEARCH_ENRICHMENT_JOB_STATUSES = ("queued", "running", "succeeded", "failed")
ELASTICSEARCH_BINDING_PROVIDERS = ("elasticsearch",)
USER_ROLES = ("admin", "moderator", "contributor")
USER_STATUSES = ("active", "suspended", "deactivated")
API_TOKEN_OWNER_TYPES = ("personal", "service_account")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def normalize_value(value: str) -> str:
    """Normalize user-facing terminology values for uniqueness checks."""

    return " ".join(value.strip().lower().split())


def normalize_profile_name(value: str) -> str:
    """Normalize profile names for human-friendly uniqueness checks.

    Profile names are commonly written either as slugs (``default_it``) or as
    display names (``Default IT``). Governance treats those forms as the same
    profile to avoid accidentally creating two terminology stores for one
    logical profile.
    """

    normalized = normalize_value(value)
    normalized = re.sub(r"[\s_-]+", "_", normalized)
    return normalized.strip("_")


class TimestampMixin:
    """Created/updated timestamps for governance rows."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TerminologyProfile(TimestampMixin, Base):
    """A logical terminology profile, for example ``default_it`` or ``payments``."""

    __tablename__ = "terminology_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    terms: Mapped[list[CanonicalTerm]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    aliases: Mapped[list[TermAlias]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    snapshots: Mapped[list[ProfileSnapshot]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    suggestions: Mapped[list[GovernanceSuggestion]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    stop_list_entries: Mapped[list[GovernanceStopListEntry]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    elasticsearch_bindings: Mapped[list[ElasticsearchBinding]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    elasticsearch_enrichment_jobs: Mapped[list[ElasticsearchEnrichmentJob]] = (
        relationship(
            back_populates="profile",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"TerminologyProfile(name={self.name!r})"


class CanonicalTerm(TimestampMixin, Base):
    """A canonical term inside a profile, such as ``kubernetes`` or ``postgresql``."""

    __tablename__ = "canonical_terms"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "normalized_value",
            name="uq_canonical_terms_profile_normalized_value",
        ),
        CheckConstraint(
            f"status IN {TERM_STATUSES!r}",
            name="canonical_term_status",
        ),
        Index("ix_canonical_terms_profile_slot", "profile_id", "slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    canonical_value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ACTIVE_STATUS, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped[TerminologyProfile] = relationship(back_populates="terms")
    aliases: Mapped[list[TermAlias]] = relationship(
        back_populates="term",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"CanonicalTerm(value={self.canonical_value!r}, slot={self.slot!r})"


class TermAlias(TimestampMixin, Base):
    """A surface form that maps to a canonical term.

    ``profile_id`` is stored redundantly on aliases so the database can enforce
    profile-wide alias uniqueness. This prevents deterministic runtime collisions
    such as ``pg`` pointing to both ``postgresql`` and ``payment-gateway``.
    """

    __tablename__ = "term_aliases"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "normalized_alias",
            name="uq_term_aliases_profile_normalized_alias",
        ),
        CheckConstraint(
            f"status IN {ALIAS_STATUSES!r}",
            name="term_alias_status",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="term_alias_confidence_range",
        ),
        Index("ix_term_aliases_term_status", "term_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_terms.id", ondelete="CASCADE"), nullable=False
    )
    alias_value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ACTIVE_STATUS, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped[TerminologyProfile] = relationship(back_populates="aliases")
    term: Mapped[CanonicalTerm] = relationship(back_populates="aliases")

    def __repr__(self) -> str:
        return f"TermAlias(alias={self.alias_value!r}, term_id={self.term_id!r})"


class GovernanceUser(TimestampMixin, Base):
    """A local governance API user for MVP authentication and role checks."""

    __tablename__ = "governance_users"
    __table_args__ = (
        CheckConstraint(
            f"role IN {USER_ROLES!r}",
            name="governance_user_role",
        ),
        CheckConstraint(
            f"status IN {USER_STATUSES!r}",
            name="governance_user_status",
        ),
        Index("ix_governance_users_normalized_username", "normalized_username"),
        Index("ix_governance_users_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    normalized_username: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tokens: Mapped[list[GovernanceAuthToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_tokens: Mapped[list[GovernanceApiToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"GovernanceUser(username={self.username!r}, role={self.role!r})"


class GovernanceAuthToken(TimestampMixin, Base):
    """A hashed bearer token issued by the governance API login endpoint."""

    __tablename__ = "governance_auth_tokens"
    __table_args__ = (
        Index("ix_governance_auth_tokens_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("governance_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped[GovernanceUser] = relationship(back_populates="tokens")

    def __repr__(self) -> str:
        return f"GovernanceAuthToken(user_id={self.user_id!r}, prefix={self.token_prefix!r})"


class GovernanceServiceAccount(TimestampMixin, Base):
    """A non-human API actor for bots, CI jobs, and migrations."""

    __tablename__ = "governance_service_accounts"
    __table_args__ = (
        CheckConstraint(
            f"role IN {USER_ROLES!r}",
            name="governance_service_account_role",
        ),
        Index(
            "ix_governance_service_accounts_normalized_name",
            "normalized_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    api_tokens: Mapped[list[GovernanceApiToken]] = relationship(
        back_populates="service_account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            "GovernanceServiceAccount("
            f"name={self.name!r}, role={self.role!r}, active={self.is_active!r})"
        )


class GovernanceApiToken(TimestampMixin, Base):
    """A hashed personal or service-account API token for external clients."""

    __tablename__ = "governance_api_tokens"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND service_account_id IS NULL) OR "
            "(user_id IS NULL AND service_account_id IS NOT NULL)",
            name="governance_api_token_single_owner",
        ),
        Index("ix_governance_api_tokens_user_created", "user_id", "created_at"),
        Index(
            "ix_governance_api_tokens_service_account_created",
            "service_account_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("governance_users.id", ondelete="CASCADE"), nullable=True
    )
    service_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("governance_service_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[GovernanceUser | None] = relationship(back_populates="api_tokens")
    service_account: Mapped[GovernanceServiceAccount | None] = relationship(
        back_populates="api_tokens"
    )

    def __repr__(self) -> str:
        owner = self.user_id if self.user_id is not None else self.service_account_id
        return f"GovernanceApiToken(name={self.name!r}, owner={owner!r})"


class GovernanceSuggestion(TimestampMixin, Base):
    """A proposed alias awaiting governance review.

    Suggestions are intentionally separate from active aliases. Contributors,
    future discovery jobs, or import tools can create suggestions without
    mutating the runtime terminology profile. Moderators/Admins approve or
    reject them later.
    """

    __tablename__ = "governance_suggestions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {SUGGESTION_STATUSES!r}",
            name="governance_suggestion_status",
        ),
        CheckConstraint(
            f"suggestion_type IN {SUGGESTION_TYPES!r}",
            name="governance_suggestion_type",
        ),
        CheckConstraint(
            f"source IN {SUGGESTION_SOURCES!r}",
            name="governance_suggestion_source",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="governance_suggestion_confidence_range",
        ),
        Index("ix_governance_suggestions_profile_status", "profile_id", "status"),
        Index(
            "ix_governance_suggestions_profile_alias",
            "profile_id",
            "normalized_alias",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_terms.id", ondelete="SET NULL"), nullable=True
    )
    alias_id: Mapped[int | None] = mapped_column(
        ForeignKey("term_aliases.id", ondelete="SET NULL"), nullable=True
    )
    suggestion_type: Mapped[str] = mapped_column(
        String(32), default="alias", nullable=False
    )
    canonical_value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_canonical: Mapped[str] = mapped_column(String(256), nullable=False)
    alias_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    normalized_alias: Mapped[str | None] = mapped_column(String(256), nullable=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped[TerminologyProfile] = relationship(back_populates="suggestions")
    term: Mapped[CanonicalTerm | None] = relationship()
    alias: Mapped[TermAlias | None] = relationship()

    def __repr__(self) -> str:
        return (
            "GovernanceSuggestion("
            f"type={self.suggestion_type!r}, canonical={self.canonical_value!r}, "
            f"alias={self.alias_value!r}, status={self.status!r})"
        )


class GovernanceStopListEntry(TimestampMixin, Base):
    """A profile-level guardrail that blocks noisy or unsafe terminology values.

    Stop-list entries are profile-scoped by default because a value that is too
    generic in one corpus can be a valid term in another. They protect manual
    edits, suggestions, and future discovery/import jobs from introducing known
    bad aliases or canonical terms.
    """

    __tablename__ = "governance_stop_list_entries"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "target",
            "normalized_value",
            name="uq_governance_stop_list_profile_target_value",
        ),
        CheckConstraint(
            f"target IN {STOP_LIST_TARGETS!r}",
            name="governance_stop_list_target",
        ),
        Index(
            "ix_governance_stop_list_profile_target_active",
            "profile_id",
            "target",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    target: Mapped[str] = mapped_column(String(32), default="both", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped[TerminologyProfile] = relationship(
        back_populates="stop_list_entries"
    )

    def __repr__(self) -> str:
        return (
            "GovernanceStopListEntry("
            f"value={self.value!r}, target={self.target!r}, active={self.is_active!r})"
        )


class GovernanceGlobalStopListEntry(TimestampMixin, Base):
    """A global guardrail that blocks noisy terminology values across profiles.

    Global stop-list entries complement profile-scoped stop lists. They are useful
    for organization-wide noise such as generic UI/log words that should never be
    introduced as aliases or canonical terms in any profile.
    """

    __tablename__ = "governance_global_stop_list_entries"
    __table_args__ = (
        UniqueConstraint(
            "target",
            "normalized_value",
            name="uq_governance_global_stop_list_target_value",
        ),
        CheckConstraint(
            f"target IN {STOP_LIST_TARGETS!r}",
            name="governance_global_stop_list_target",
        ),
        Index(
            "ix_governance_global_stop_list_target_active",
            "target",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    target: Mapped[str] = mapped_column(String(32), default="both", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return (
            "GovernanceGlobalStopListEntry("
            f"value={self.value!r}, target={self.target!r}, "
            f"active={self.is_active!r})"
        )


class ElasticsearchBinding(TimestampMixin, Base):
    """A saved enrichment target that binds a profile to Elasticsearch documents.

    Bindings are configuration-only in the first API patch. They describe where
    a terminology profile should be applied later by enrichment jobs, without
    opening an Elasticsearch connection or writing to an index yet.
    """

    __tablename__ = "elasticsearch_bindings"
    __table_args__ = (
        UniqueConstraint(
            "normalized_name",
            name="uq_elasticsearch_bindings_normalized_name",
        ),
        CheckConstraint(
            "provider IN ('elasticsearch')",
            name="elasticsearch_binding_provider",
        ),
        CheckConstraint(
            f"mode IN {ELASTICSEARCH_BINDING_MODES!r}",
            name="elasticsearch_binding_mode",
        ),
        CheckConstraint(
            f"write_strategy IN {ELASTICSEARCH_BINDING_WRITE_STRATEGIES!r}",
            name="elasticsearch_binding_write_strategy",
        ),
        Index("ix_elasticsearch_bindings_profile_enabled", "profile_id", "is_enabled"),
        Index("ix_elasticsearch_bindings_index", "index_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(
        String(32), default="elasticsearch", nullable=False
    )
    index_name: Mapped[str] = mapped_column(String(256), nullable=False)
    text_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target_field: Mapped[str] = mapped_column(String(256), nullable=False)
    filter_field: Mapped[str | None] = mapped_column(String(256), nullable=True)
    filter_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timestamp_field: Mapped[str | None] = mapped_column(String(256), nullable=True)
    time_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="dry_run", nullable=False)
    write_strategy: Mapped[str] = mapped_column(
        String(32), default="reindex_alias_swap", nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped[TerminologyProfile] = relationship(
        back_populates="elasticsearch_bindings"
    )
    enrichment_jobs: Mapped[list[ElasticsearchEnrichmentJob]] = relationship(
        back_populates="binding",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            "ElasticsearchBinding("
            f"name={self.name!r}, profile_id={self.profile_id!r}, "
            f"index={self.index_name!r}, mode={self.mode!r}, "
            f"write_strategy={self.write_strategy!r}, "
            f"timestamp_field={self.timestamp_field!r}, "
            f"time_window_days={self.time_window_days!r})"
        )


class ElasticsearchEnrichmentJob(TimestampMixin, Base):
    """A synchronous MVP control-plane record for Elasticsearch enrichment jobs.

    The first job implementation runs inside the API process and records the
    result in the database. Celery/RabbitMQ workers can later execute the same
    job contract asynchronously without changing the stored API shape.
    """

    __tablename__ = "elasticsearch_enrichment_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ELASTICSEARCH_ENRICHMENT_JOB_STATUSES!r}",
            name="elasticsearch_enrichment_job_status",
        ),
        CheckConstraint(
            f"write_strategy IN {ELASTICSEARCH_BINDING_WRITE_STRATEGIES!r}",
            name="elasticsearch_enrichment_job_write_strategy",
        ),
        Index(
            "ix_elasticsearch_enrichment_jobs_binding_created",
            "binding_id",
            "created_at",
        ),
        Index("ix_elasticsearch_enrichment_jobs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    binding_id: Mapped[int] = mapped_column(
        ForeignKey("elasticsearch_bindings.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    write_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    source_index: Mapped[str] = mapped_column(String(256), nullable=False)
    target_index: Mapped[str | None] = mapped_column(String(256), nullable=True)
    alias_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    documents_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_enriched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    binding: Mapped[ElasticsearchBinding] = relationship(
        back_populates="enrichment_jobs"
    )
    profile: Mapped[TerminologyProfile] = relationship(
        back_populates="elasticsearch_enrichment_jobs"
    )

    def __repr__(self) -> str:
        return (
            "ElasticsearchEnrichmentJob("
            f"binding_id={self.binding_id!r}, status={self.status!r}, "
            f"write_strategy={self.write_strategy!r})"
        )


class ProfileSnapshot(TimestampMixin, Base):
    """A versioned runtime snapshot exported from governance data."""

    __tablename__ = "profile_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "version",
            name="uq_profile_snapshots_profile_version",
        ),
        CheckConstraint(
            f"status IN {SNAPSHOT_STATUSES!r}",
            name="profile_snapshot_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="postgres", nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped[TerminologyProfile] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:
        return f"ProfileSnapshot(version={self.version!r}, status={self.status!r})"


class AuditEvent(Base):
    """Append-only governance audit event."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("terminology_profiles.id", ondelete="CASCADE"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    profile: Mapped[TerminologyProfile | None] = relationship(
        back_populates="audit_events"
    )

    def __repr__(self) -> str:
        return f"AuditEvent(action={self.action!r}, entity_type={self.entity_type!r})"


def _fill_normalized_profile(
    mapper: Any, connection: Any, target: TerminologyProfile
) -> None:
    del mapper, connection
    target.normalized_name = normalize_profile_name(target.name)


def _fill_normalized_term(mapper: Any, connection: Any, target: CanonicalTerm) -> None:
    del mapper, connection
    target.normalized_value = normalize_value(target.canonical_value)
    target.slot = target.slot.strip().upper()


def _fill_normalized_alias(mapper: Any, connection: Any, target: TermAlias) -> None:
    del mapper, connection
    target.normalized_alias = normalize_value(target.alias_value)


def _fill_normalized_user(mapper: Any, connection: Any, target: GovernanceUser) -> None:
    del mapper, connection
    target.normalized_username = normalize_profile_name(target.username)
    if target.status:
        target.status = target.status.strip().lower()
    else:
        target.status = "suspended" if target.is_active is False else "active"
    target.is_active = target.status == "active"


def _fill_normalized_service_account(
    mapper: Any, connection: Any, target: GovernanceServiceAccount
) -> None:
    del mapper, connection
    target.normalized_name = normalize_profile_name(target.name)


def _fill_normalized_api_token(
    mapper: Any, connection: Any, target: GovernanceApiToken
) -> None:
    del mapper, connection
    target.name = target.name.strip()
    target.scopes = sorted(
        {scope.strip() for scope in (target.scopes or []) if scope.strip()}
    )


def _fill_normalized_suggestion(
    mapper: Any, connection: Any, target: GovernanceSuggestion
) -> None:
    del mapper, connection
    target.normalized_canonical = normalize_value(target.canonical_value)
    target.normalized_alias = (
        normalize_value(target.alias_value) if target.alias_value is not None else None
    )
    target.slot = target.slot.strip().upper()


def _fill_normalized_stop_list_entry(
    mapper: Any, connection: Any, target: GovernanceStopListEntry
) -> None:
    del mapper, connection
    target.normalized_value = normalize_value(target.value)


def _fill_normalized_global_stop_list_entry(
    mapper: Any, connection: Any, target: GovernanceGlobalStopListEntry
) -> None:
    del mapper, connection
    target.normalized_value = normalize_value(target.value)


def _fill_normalized_elasticsearch_binding(
    mapper: Any, connection: Any, target: ElasticsearchBinding
) -> None:
    del mapper, connection
    target.normalized_name = normalize_profile_name(target.name)
    target.provider = (target.provider or "elasticsearch").strip().lower()
    target.index_name = target.index_name.strip()
    target.text_fields = [
        field.strip()
        for field in (target.text_fields or [])
        if isinstance(field, str) and field.strip()
    ]
    target.target_field = target.target_field.strip()
    target.filter_field = target.filter_field.strip() if target.filter_field else None
    target.filter_value = target.filter_value.strip() if target.filter_value else None
    target.mode = (target.mode or "dry_run").strip().lower()
    target.write_strategy = (
        (target.write_strategy or "reindex_alias_swap").strip().lower()
    )


event.listen(TerminologyProfile, "before_insert", _fill_normalized_profile)
event.listen(TerminologyProfile, "before_update", _fill_normalized_profile)
event.listen(CanonicalTerm, "before_insert", _fill_normalized_term)
event.listen(CanonicalTerm, "before_update", _fill_normalized_term)
event.listen(TermAlias, "before_insert", _fill_normalized_alias)
event.listen(TermAlias, "before_update", _fill_normalized_alias)

event.listen(GovernanceUser, "before_insert", _fill_normalized_user)
event.listen(GovernanceUser, "before_update", _fill_normalized_user)
event.listen(
    GovernanceServiceAccount, "before_insert", _fill_normalized_service_account
)
event.listen(
    GovernanceServiceAccount, "before_update", _fill_normalized_service_account
)
event.listen(GovernanceApiToken, "before_insert", _fill_normalized_api_token)
event.listen(GovernanceApiToken, "before_update", _fill_normalized_api_token)
event.listen(GovernanceSuggestion, "before_insert", _fill_normalized_suggestion)
event.listen(GovernanceSuggestion, "before_update", _fill_normalized_suggestion)
event.listen(GovernanceStopListEntry, "before_insert", _fill_normalized_stop_list_entry)
event.listen(GovernanceStopListEntry, "before_update", _fill_normalized_stop_list_entry)
event.listen(
    GovernanceGlobalStopListEntry,
    "before_insert",
    _fill_normalized_global_stop_list_entry,
)
event.listen(
    GovernanceGlobalStopListEntry,
    "before_update",
    _fill_normalized_global_stop_list_entry,
)
event.listen(
    ElasticsearchBinding, "before_insert", _fill_normalized_elasticsearch_binding
)
event.listen(
    ElasticsearchBinding, "before_update", _fill_normalized_elasticsearch_binding
)
