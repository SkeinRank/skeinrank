"""SQLAlchemy models for SkeinRank terminology governance.

The database is a control plane for terminology editing and snapshot publishing.
Hot-path extraction should continue to load an exported snapshot and build an
in-memory matcher.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
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


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def normalize_value(value: str) -> str:
    """Normalize user-facing terminology values for uniqueness checks."""

    return " ".join(value.strip().lower().split())


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
    target.normalized_name = normalize_value(target.name)


def _fill_normalized_term(mapper: Any, connection: Any, target: CanonicalTerm) -> None:
    del mapper, connection
    target.normalized_value = normalize_value(target.canonical_value)
    target.slot = target.slot.strip().upper()


def _fill_normalized_alias(mapper: Any, connection: Any, target: TermAlias) -> None:
    del mapper, connection
    target.normalized_alias = normalize_value(target.alias_value)


event.listen(TerminologyProfile, "before_insert", _fill_normalized_profile)
event.listen(TerminologyProfile, "before_update", _fill_normalized_profile)
event.listen(CanonicalTerm, "before_insert", _fill_normalized_term)
event.listen(CanonicalTerm, "before_update", _fill_normalized_term)
event.listen(TermAlias, "before_insert", _fill_normalized_alias)
event.listen(TermAlias, "before_update", _fill_normalized_alias)
