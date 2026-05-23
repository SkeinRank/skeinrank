"""Bridge proposal conflicts into ambiguous alias candidate records.

This module keeps the proposal pipeline side-effect controlled: submitting a
proposal may create reviewer-facing ambiguous-alias candidates, but it never
changes active aliases or runtime snapshots. Binding policy/runtime resolution is
left to later coverage phases.
"""

from __future__ import annotations

from typing import Any

from skeinrank_governance.models import (
    CanonicalTerm,
    GovernanceAmbiguousAlias,
    GovernanceAmbiguousAliasCandidate,
    GovernanceSuggestion,
    TermAlias,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def sync_ambiguous_alias_candidates_for_suggestion(
    session: Session,
    suggestion: GovernanceSuggestion,
    *,
    actor: str | None = None,
) -> GovernanceAmbiguousAlias | None:
    """Record ambiguous alias candidates when a proposal reveals ambiguity.

    The function is intentionally conservative. It only creates/updates
    ``GovernanceAmbiguousAlias`` rows for alias proposals where the same surface
    form points to more than one canonical interpretation either through an
    active alias or through another pending proposal. It does not approve,
    reject, or apply the proposal.
    """

    if suggestion.suggestion_type != "alias":
        return None
    if not suggestion.alias_value or not suggestion.normalized_alias:
        return None

    normalized_alias = suggestion.normalized_alias
    candidate_specs: dict[tuple[str, str], dict[str, Any]] = {}

    active_alias = session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == suggestion.profile_id,
            TermAlias.normalized_alias == normalized_alias,
        )
    )
    if active_alias is not None and active_alias.term is not None:
        _merge_candidate_spec(
            candidate_specs,
            canonical_value=active_alias.term.canonical_value,
            slot=active_alias.term.slot,
            term_id=active_alias.term_id,
            source="active_alias",
            status="preferred",
            confidence=active_alias.confidence,
            evidence={
                "reason": "active_alias_conflict",
                "alias_id": active_alias.id,
                "term_id": active_alias.term_id,
                "alias_value": active_alias.alias_value,
            },
        )

    pending_suggestions = list(
        session.scalars(
            select(GovernanceSuggestion).where(
                GovernanceSuggestion.profile_id == suggestion.profile_id,
                GovernanceSuggestion.suggestion_type == "alias",
                GovernanceSuggestion.normalized_alias == normalized_alias,
                GovernanceSuggestion.status == "pending",
            )
        )
    )
    for pending in pending_suggestions:
        if pending.normalized_canonical is None:
            continue
        pending_term_id = pending.term_id or _find_term_id(
            session,
            profile_id=suggestion.profile_id,
            normalized_canonical=pending.normalized_canonical,
            slot=pending.slot,
        )
        _merge_candidate_spec(
            candidate_specs,
            canonical_value=pending.canonical_value,
            slot=pending.slot,
            term_id=pending_term_id,
            source="suggestion",
            status="candidate",
            confidence=pending.confidence,
            evidence={
                "reason": "pending_proposal_candidate",
                "suggestion_id": pending.id,
                "proposal_source_type": pending.proposal_source_type,
                "proposal_source_name": pending.proposal_source_name,
            },
        )

    if len(candidate_specs) < 2:
        return None

    ambiguous_alias = session.scalar(
        select(GovernanceAmbiguousAlias).where(
            GovernanceAmbiguousAlias.profile_id == suggestion.profile_id,
            GovernanceAmbiguousAlias.normalized_surface == normalized_alias,
        )
    )
    if ambiguous_alias is None:
        ambiguous_alias = GovernanceAmbiguousAlias(
            profile=suggestion.profile,
            surface_value=suggestion.alias_value,
            normalized_surface=normalized_alias,
            status="open",
            created_by=actor or suggestion.created_by,
            review_note="Created from conflicting alias proposal candidates.",
        )
        session.add(ambiguous_alias)
        session.flush()
    else:
        ambiguous_alias.surface_value = suggestion.alias_value

    existing_by_key = {
        (candidate.normalized_canonical, candidate.slot): candidate
        for candidate in ambiguous_alias.candidates
    }
    for key, spec in candidate_specs.items():
        candidate = existing_by_key.get(key)
        if candidate is None:
            candidate = GovernanceAmbiguousAliasCandidate(
                ambiguous_alias=ambiguous_alias,
                canonical_value=spec["canonical_value"],
                normalized_canonical=key[0],
                slot=key[1],
            )
            session.add(candidate)
        _apply_candidate_spec(candidate, spec)

    session.flush()
    return ambiguous_alias


def _merge_candidate_spec(
    specs: dict[tuple[str, str], dict[str, Any]],
    *,
    canonical_value: str,
    slot: str,
    term_id: int | None,
    source: str,
    status: str,
    confidence: float,
    evidence: dict[str, Any],
) -> None:
    normalized_canonical = normalize_value(canonical_value)
    normalized_slot = slot.strip().upper()
    key = (normalized_canonical, normalized_slot)
    existing = specs.get(key)
    next_spec = {
        "canonical_value": canonical_value,
        "slot": normalized_slot,
        "term_id": term_id,
        "source": source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
    }
    if existing is None:
        specs[key] = next_spec
        return

    # Active runtime state is more authoritative than a proposal candidate.
    if existing["source"] == "active_alias":
        existing["confidence"] = max(float(existing["confidence"]), confidence)
        return
    if source == "active_alias":
        specs[key] = next_spec
        return

    existing["confidence"] = max(float(existing["confidence"]), confidence)
    existing["evidence"] = {
        **dict(existing.get("evidence") or {}),
        "additional_suggestion_id": evidence.get("suggestion_id"),
    }


def _apply_candidate_spec(
    candidate: GovernanceAmbiguousAliasCandidate,
    spec: dict[str, Any],
) -> None:
    # Do not downgrade an active alias interpretation if a later proposal repeats
    # the same canonical/slot candidate.
    if candidate.source == "active_alias" and spec["source"] != "active_alias":
        candidate.confidence = max(candidate.confidence, float(spec["confidence"]))
        return

    candidate.term_id = spec["term_id"]
    candidate.canonical_value = spec["canonical_value"]
    candidate.normalized_canonical = normalize_value(spec["canonical_value"])
    candidate.slot = spec["slot"]
    candidate.source = spec["source"]
    candidate.status = spec["status"]
    candidate.confidence = float(spec["confidence"])
    candidate.evidence_json = spec["evidence"]


def _find_term_id(
    session: Session,
    *,
    profile_id: int,
    normalized_canonical: str,
    slot: str,
) -> int | None:
    term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile_id,
            CanonicalTerm.normalized_value == normalized_canonical,
            CanonicalTerm.slot == slot.strip().upper(),
        )
    )
    return term.id if term is not None else None
