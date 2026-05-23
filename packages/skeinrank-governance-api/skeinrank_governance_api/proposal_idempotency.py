"""Idempotency helpers for proposal submission endpoints.

Agents and CI jobs may retry proposal submissions when a network request times
out. These helpers make retries safe by returning the already-created proposal
when the idempotency key and core proposal payload match, and by rejecting reuse
of the same key for a different proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import (
    GovernanceSuggestion,
    TerminologyProfile,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ProposalIdempotencyConflict(Exception):
    """Raised when an idempotency key is reused for a different proposal."""

    idempotency_key: str
    existing_suggestion_id: int

    def __str__(self) -> str:
        return (
            "Idempotency key is already used for a different proposal: "
            f"{self.idempotency_key!r} (existing suggestion: "
            f"{self.existing_suggestion_id})"
        )


def normalize_idempotency_key(value: str | None) -> str | None:
    """Normalize optional idempotency keys while preserving caller semantics."""

    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def find_existing_idempotent_suggestion(
    session: Session,
    *,
    profile: TerminologyProfile,
    idempotency_key: str | None,
) -> GovernanceSuggestion | None:
    """Return an existing suggestion for the profile/key pair, if any."""

    key = normalize_idempotency_key(idempotency_key)
    if key is None:
        return None
    return session.scalar(
        select(GovernanceSuggestion).where(
            GovernanceSuggestion.profile_id == profile.id,
            GovernanceSuggestion.idempotency_key == key,
        )
    )


def ensure_idempotent_retry_or_raise(
    existing: GovernanceSuggestion | None,
    *,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    binding_id: int | None,
    proposal_source_type: str,
) -> GovernanceSuggestion | None:
    """Return the existing suggestion if a retry matches, otherwise fail.

    The comparison intentionally focuses on the stable proposal identity rather
    than mutable review metadata such as evidence, context, or comments.
    """

    if existing is None:
        return None

    expected = _proposal_identity(
        suggestion_type=suggestion_type,
        canonical_value=canonical_value,
        alias_value=alias_value,
        slot=slot,
        binding_id=binding_id,
        proposal_source_type=proposal_source_type,
    )
    actual = _proposal_identity(
        suggestion_type=existing.suggestion_type,
        canonical_value=existing.canonical_value,
        alias_value=existing.alias_value,
        slot=existing.slot,
        binding_id=existing.binding_id,
        proposal_source_type=existing.proposal_source_type,
    )
    if expected == actual:
        return existing

    raise ProposalIdempotencyConflict(
        idempotency_key=str(existing.idempotency_key or ""),
        existing_suggestion_id=existing.id,
    )


def resolve_idempotent_suggestion(
    session: Session,
    *,
    profile: TerminologyProfile,
    idempotency_key: str | None,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    binding_id: int | None,
    proposal_source_type: str,
) -> GovernanceSuggestion | None:
    """Find and validate an existing proposal for a retry, if one exists."""

    existing = find_existing_idempotent_suggestion(
        session,
        profile=profile,
        idempotency_key=idempotency_key,
    )
    return ensure_idempotent_retry_or_raise(
        existing,
        suggestion_type=suggestion_type,
        canonical_value=canonical_value,
        alias_value=alias_value,
        slot=slot,
        binding_id=binding_id,
        proposal_source_type=proposal_source_type,
    )


def resolve_idempotent_suggestion_from_validation_summary(
    session: Session,
    validation_summary: dict[str, Any] | None,
    *,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    binding_id: int | None,
    proposal_source_type: str,
) -> GovernanceSuggestion | None:
    """Resolve an existing suggestion referenced by validation output.

    This is a defensive fallback for retry paths: the checker registry can
    identify an existing proposal before creation, and this helper turns that
    checker result into the same idempotent retry/409 behavior as the direct
    profile/key lookup.
    """

    existing_id = _existing_suggestion_id_from_validation_summary(validation_summary)
    if existing_id is None:
        return None

    existing = session.get(GovernanceSuggestion, existing_id)
    return ensure_idempotent_retry_or_raise(
        existing,
        suggestion_type=suggestion_type,
        canonical_value=canonical_value,
        alias_value=alias_value,
        slot=slot,
        binding_id=binding_id,
        proposal_source_type=proposal_source_type,
    )


def _existing_suggestion_id_from_validation_summary(
    validation_summary: dict[str, Any] | None,
) -> int | None:
    if not isinstance(validation_summary, dict):
        return None
    checks = validation_summary.get("checks")
    if not isinstance(checks, dict):
        return None
    idempotency_check = checks.get("idempotency_key")
    if not isinstance(idempotency_check, dict):
        return None
    details = idempotency_check.get("details")
    if not isinstance(details, dict):
        return None
    existing_id = details.get("existing_suggestion_id")
    if isinstance(existing_id, int):
        return existing_id
    return None


def _proposal_identity(
    *,
    suggestion_type: str,
    canonical_value: str,
    alias_value: str | None,
    slot: str,
    binding_id: int | None,
    proposal_source_type: str,
) -> dict[str, Any]:
    return {
        "suggestion_type": suggestion_type,
        "normalized_canonical": normalize_value(canonical_value),
        "normalized_alias": normalize_value(alias_value) if alias_value else None,
        "slot": slot.strip().upper(),
        "binding_id": binding_id,
        "proposal_source_type": proposal_source_type,
    }
