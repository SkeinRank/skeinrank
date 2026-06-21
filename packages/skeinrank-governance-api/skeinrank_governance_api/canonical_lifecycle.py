"""Canonical lifecycle helpers for reviewed terminology migrations.

Canonical migration keeps the runtime safe by treating a canonical rename as a
reviewed proposal. The old canonical term is deprecated, all historical surfaces
are preserved as aliases, and the new canonical becomes the active runtime term.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import (
    CanonicalTerm,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

CANONICAL_LIFECYCLE_SCHEMA_VERSION = "skeinrank.canonical_lifecycle.v1"
CANONICAL_MIGRATION_ACTION = "canonical_migration"


class CanonicalLifecycleError(ValueError):
    """Raised when a canonical lifecycle plan cannot be built or applied."""


@dataclass(frozen=True)
class CanonicalMigrationPlan:
    """Reviewer-facing plan for moving an object to a new canonical surface."""

    old_canonical_value: str
    new_canonical_value: str
    slot: str
    old_term_id: int
    new_term_id: int | None
    old_status: str
    new_status: str | None
    aliases_to_preserve: tuple[str, ...]
    alias_conflicts: tuple[dict[str, Any], ...]
    evidence: Mapping[str, Any]

    @property
    def is_blocked(self) -> bool:
        """Return whether deterministic conflicts make the migration unsafe."""

        return bool(self.alias_conflicts)

    def to_source_payload(self) -> dict[str, Any]:
        """Serialize the plan into a stable proposal source payload."""

        return {
            "schema_version": CANONICAL_LIFECYCLE_SCHEMA_VERSION,
            "action": CANONICAL_MIGRATION_ACTION,
            "risk_flags": ["canonical_migration"],
            "old_canonical_value": self.old_canonical_value,
            "new_canonical_value": self.new_canonical_value,
            "slot": self.slot,
            "old_term_id": self.old_term_id,
            "new_term_id": self.new_term_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "demote_old_canonical_to_alias": True,
            "preserve_historical_aliases": True,
            "aliases_to_preserve": list(self.aliases_to_preserve),
            "alias_conflicts": list(self.alias_conflicts),
            "evidence": dict(self.evidence),
            "operator_rule": (
                "Canonical follows documents. Aliases preserve humans. "
                "Snapshots make migration safe."
            ),
        }


def is_canonical_migration_payload(source_payload: object) -> bool:
    """Return whether a proposal source payload encodes a canonical migration."""

    if not isinstance(source_payload, Mapping):
        return False
    return (
        source_payload.get("schema_version") == CANONICAL_LIFECYCLE_SCHEMA_VERSION
        and source_payload.get("action") == CANONICAL_MIGRATION_ACTION
    )


def is_canonical_migration_suggestion(suggestion: GovernanceSuggestion) -> bool:
    """Return whether a governance suggestion is a canonical migration proposal."""

    return is_canonical_migration_payload(suggestion.source_payload_json)


def build_canonical_migration_plan(
    session: Session,
    profile: TerminologyProfile,
    *,
    old_canonical_value: str,
    new_canonical_value: str,
    slot: str | None = None,
    extra_aliases_to_preserve: Iterable[str] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> CanonicalMigrationPlan:
    """Build a deterministic, side-effect-free canonical migration plan."""

    old_value = old_canonical_value.strip()
    new_value = new_canonical_value.strip()
    if not old_value:
        raise CanonicalLifecycleError("old_canonical_value is required.")
    if not new_value:
        raise CanonicalLifecycleError("new_canonical_value is required.")
    if normalize_value(old_value) == normalize_value(new_value):
        raise CanonicalLifecycleError(
            "old_canonical_value and new_canonical_value must be different."
        )

    old_term = _get_term_by_value(session, profile, old_value)
    if old_term is None:
        raise CanonicalLifecycleError(
            f"Old canonical term not found in profile {profile.name!r}: {old_value}"
        )
    if old_term.status != "active":
        raise CanonicalLifecycleError(
            "Only active canonical terms can be migrated. "
            f"Current status for {old_term.canonical_value!r}: {old_term.status}"
        )

    normalized_slot = (slot or old_term.slot).strip().upper()
    if normalized_slot != old_term.slot:
        raise CanonicalLifecycleError(
            "Migration slot must match the old canonical term slot. "
            f"Expected {old_term.slot!r}, got {normalized_slot!r}."
        )

    new_term = _get_term_by_value(session, profile, new_value)
    if new_term is not None and new_term.slot != normalized_slot:
        raise CanonicalLifecycleError(
            "New canonical term already exists with a different slot. "
            f"Expected {normalized_slot!r}, found {new_term.slot!r}."
        )

    aliases_to_preserve = _migration_alias_values(
        old_term,
        extra_aliases=extra_aliases_to_preserve,
    )
    allowed_term_ids = {old_term.id}
    if new_term is not None:
        allowed_term_ids.add(new_term.id)
    conflicts = _alias_conflicts_for_values(
        session,
        profile,
        aliases_to_preserve,
        allowed_term_ids=allowed_term_ids,
    )
    return CanonicalMigrationPlan(
        old_canonical_value=old_term.canonical_value,
        new_canonical_value=new_value,
        slot=normalized_slot,
        old_term_id=old_term.id,
        new_term_id=new_term.id if new_term is not None else None,
        old_status=old_term.status,
        new_status=new_term.status if new_term is not None else None,
        aliases_to_preserve=tuple(aliases_to_preserve),
        alias_conflicts=tuple(conflicts),
        evidence=dict(evidence or {}),
    )


def build_canonical_migration_validation_summary(
    plan: CanonicalMigrationPlan,
) -> dict[str, Any]:
    """Return a proposal validation summary for a migration plan."""

    checks: dict[str, Any] = {
        "canonical_migration": {
            "status": "warning",
            "severity": "warning",
            "message": (
                "Canonical migration changes runtime canonicalization and requires "
                "explicit reviewer confirmation."
            ),
            "details": {
                "risk_flags": ["canonical_migration"],
                "old_canonical_value": plan.old_canonical_value,
                "new_canonical_value": plan.new_canonical_value,
                "aliases_to_preserve": list(plan.aliases_to_preserve),
            },
        }
    }
    blocked = 0
    warnings = 1
    if plan.alias_conflicts:
        checks["alias_conflicts"] = {
            "status": "blocked",
            "severity": "error",
            "message": (
                "Some preserved aliases already point to another canonical term."
            ),
            "details": {"conflicts": list(plan.alias_conflicts)},
        }
        blocked += 1

    status = "blocked" if blocked else "warning"
    return {
        "schema_version": "skeinrank.proposal_validation.v1",
        "status": status,
        "counts": {"passed": 1, "warning": warnings, "blocked": blocked},
        "checks": checks,
    }


def apply_canonical_migration_suggestion(
    session: Session,
    profile: TerminologyProfile,
    suggestion: GovernanceSuggestion,
) -> dict[str, Any]:
    """Apply a reviewed canonical migration proposal in one transaction."""

    payload = suggestion.source_payload_json or {}
    if not is_canonical_migration_payload(payload):
        raise CanonicalLifecycleError(
            "Suggestion is not a canonical migration proposal."
        )

    old_value = str(payload.get("old_canonical_value") or "").strip()
    new_value = str(
        payload.get("new_canonical_value") or suggestion.canonical_value
    ).strip()
    aliases_to_preserve = [
        str(value)
        for value in payload.get("aliases_to_preserve") or []
        if str(value).strip()
    ]
    plan = build_canonical_migration_plan(
        session,
        profile,
        old_canonical_value=old_value,
        new_canonical_value=new_value,
        slot=suggestion.slot,
        extra_aliases_to_preserve=aliases_to_preserve,
        evidence=(
            payload.get("evidence")
            if isinstance(payload.get("evidence"), Mapping)
            else {}
        ),
    )
    if plan.alias_conflicts:
        raise CanonicalLifecycleError(
            "Canonical migration has alias conflicts and cannot be applied."
        )

    old_term = _get_term_by_value(session, profile, plan.old_canonical_value)
    if old_term is None:  # pragma: no cover - guarded by plan builder
        raise CanonicalLifecycleError("Old canonical term disappeared before apply.")
    new_term = _get_term_by_value(session, profile, plan.new_canonical_value)
    created_new_term = False
    if new_term is None:
        new_term = CanonicalTerm(
            profile=profile,
            canonical_value=plan.new_canonical_value,
            slot=plan.slot,
            description=suggestion.description,
            status="active",
        )
        session.add(new_term)
        session.flush()
        created_new_term = True
    elif new_term.status != "active":
        new_term.status = "active"

    preserved_alias_ids: list[int] = []
    created_alias_ids: list[int] = []
    for alias_value in plan.aliases_to_preserve:
        alias, created = _upsert_preserved_alias(
            session,
            profile,
            old_term=old_term,
            new_term=new_term,
            alias_value=alias_value,
            confidence=suggestion.confidence,
            notes=suggestion.context,
        )
        preserved_alias_ids.append(alias.id)
        if created:
            created_alias_ids.append(alias.id)

    old_term.status = "deprecated"
    suggestion.term_id = new_term.id
    if created_alias_ids:
        suggestion.alias_id = created_alias_ids[0]
    elif preserved_alias_ids:
        suggestion.alias_id = preserved_alias_ids[0]

    applied_payload = {
        "schema_version": CANONICAL_LIFECYCLE_SCHEMA_VERSION,
        "action": CANONICAL_MIGRATION_ACTION,
        "old_term_id": old_term.id,
        "new_term_id": new_term.id,
        "old_canonical_value": old_term.canonical_value,
        "new_canonical_value": new_term.canonical_value,
        "old_term_status": old_term.status,
        "new_term_status": new_term.status,
        "created_new_term": created_new_term,
        "preserved_alias_ids": preserved_alias_ids,
        "created_alias_ids": created_alias_ids,
        "aliases_to_preserve": list(plan.aliases_to_preserve),
    }
    suggestion.source_payload_json = {
        **payload,
        "applied_payload": applied_payload,
    }
    return applied_payload


def _get_term_by_value(
    session: Session,
    profile: TerminologyProfile,
    canonical_value: str,
) -> CanonicalTerm | None:
    return session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == normalize_value(canonical_value),
        )
    )


def _migration_alias_values(
    old_term: CanonicalTerm,
    *,
    extra_aliases: Iterable[str] | None = None,
) -> list[str]:
    values: list[str] = [old_term.canonical_value]
    values.extend(
        alias.alias_value
        for alias in old_term.aliases
        if alias.status in {"active", "deprecated", "pending"}
    )
    values.extend(str(value) for value in extra_aliases or [])
    normalized_seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_value(value)
        if not normalized or normalized in normalized_seen:
            continue
        normalized_seen.add(normalized)
        result.append(str(value).strip())
    return result


def _alias_conflicts_for_values(
    session: Session,
    profile: TerminologyProfile,
    alias_values: Iterable[str],
    *,
    allowed_term_ids: set[int],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    seen_normalized: set[str] = set()
    for alias_value in alias_values:
        normalized = normalize_value(alias_value)
        if not normalized or normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        existing = session.scalar(
            select(TermAlias).where(
                TermAlias.profile_id == profile.id,
                TermAlias.normalized_alias == normalized,
            )
        )
        if existing is None or existing.term_id in allowed_term_ids:
            continue
        conflicts.append(
            {
                "alias_value": existing.alias_value,
                "normalized_alias": existing.normalized_alias,
                "term_id": existing.term_id,
                "canonical_value": existing.term.canonical_value
                if existing.term is not None
                else None,
            }
        )
    return conflicts


def _upsert_preserved_alias(
    session: Session,
    profile: TerminologyProfile,
    *,
    old_term: CanonicalTerm,
    new_term: CanonicalTerm,
    alias_value: str,
    confidence: float,
    notes: str | None,
) -> tuple[TermAlias, bool]:
    normalized = normalize_value(alias_value)
    existing = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == normalized,
        )
    )
    if existing is not None:
        if existing.term_id not in {old_term.id, new_term.id}:
            raise CanonicalLifecycleError(
                f"Alias already points to another canonical term: {alias_value}"
            )
        existing.term = new_term
        existing.status = "active"
        existing.confidence = max(existing.confidence or 0.0, confidence)
        if notes and not existing.notes:
            existing.notes = notes
        session.flush()
        return existing, False

    alias = TermAlias(
        profile=profile,
        term=new_term,
        alias_value=alias_value,
        confidence=confidence,
        status="active",
        notes=notes,
    )
    session.add(alias)
    session.flush()
    return alias, True
