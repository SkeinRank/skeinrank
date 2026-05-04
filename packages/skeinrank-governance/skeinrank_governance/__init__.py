"""Terminology governance storage primitives for SkeinRank.

This package is the platform foundation for future Postgres-backed terminology
management. Runtime extraction still uses exported snapshots; the database is a
control-plane source of truth.
"""

from .db import Base, create_all, create_governance_engine, create_session_factory
from .models import (
    ACTIVE_STATUS,
    ALIAS_STATUSES,
    SNAPSHOT_STATUSES,
    TERM_STATUSES,
    AuditEvent,
    CanonicalTerm,
    ProfileSnapshot,
    TermAlias,
    TerminologyProfile,
    normalize_value,
)

__all__ = [
    "ACTIVE_STATUS",
    "ALIAS_STATUSES",
    "Base",
    "AuditEvent",
    "CanonicalTerm",
    "ProfileSnapshot",
    "SNAPSHOT_STATUSES",
    "TERM_STATUSES",
    "TermAlias",
    "TerminologyProfile",
    "create_all",
    "create_governance_engine",
    "create_session_factory",
    "normalize_value",
]
